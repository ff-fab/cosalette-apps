"""Application settings for wiz2mqtt.

Extends cosalette's Settings with the WIZ2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or a TOML
config file (bulb and group inventory). Priority: CLI > env > .env >
wiz2mqtt.toml > defaults.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from collections import Counter
from typing import Annotated, Any, Literal, cast

import cosalette
from pydantic import BaseModel, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
_MAC_RE = re.compile(r"[0-9A-Fa-f]{12}")
# Mirrors cosalette's MqttSettings.topic_prefix check (_settings/__init__.py),
# but non-empty: signal_topic is a specific topic, not an optional prefix.
_SIGNAL_TOPIC_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")
_APP_NAME = "wiz2mqtt"
"""The topic prefix cosalette falls back to when ``mqtt.topic_prefix`` is unset."""


class BulbConfig(BaseModel):
    """Configuration for a single WiZ bulb.

    ``ip`` is the bulb's identity; ``mac``, when given, is used to verify
    that identity against the bulb's own reported MAC on first contact.
    """

    # Mirrors jeelink2mqtt's name validator; keep in sync until a shared utility exists.
    name: Annotated[str, Field(max_length=64)]
    ip: str
    mac: str | None = None
    power_source: str | None = Field(
        default=None,
        description=(
            "Name of a [[power_sources]] entry that powers this bulb directly. "
            "Wins over any [[power_sources]] block that claims the bulb's "
            "group (ADR-007)."
        ),
    )
    restore_previous_state: bool = Field(
        default=False,
        description=(
            "Restore the bulb's previous desired state when it returns to "
            "reachability with no queued command (ADR-008)."
        ),
    )

    @field_validator("name")
    @classmethod
    def _name_must_be_valid_topic_segment(cls, value: str) -> str:
        """Reject names that would form invalid MQTT topic segments."""
        if not _NAME_RE.fullmatch(value):
            raise ValueError(
                "Bulb name must be a non-empty MQTT topic segment "
                "matching [A-Za-z0-9_-]+ (no '/', '+', '#', whitespace, "
                "or control chars)"
            )
        return value

    @field_validator("ip")
    @classmethod
    def _ip_must_be_valid_ipv4(cls, value: str) -> str:
        """Reject anything that isn't a literal IPv4 address."""
        try:
            # Return canonical form; Python ≥3.9 rejects non-decimal representations.
            return str(ipaddress.IPv4Address(value))
        except ValueError as exc:
            msg = f"Bulb ip must be a valid IPv4 address, got {value!r}"
            raise ValueError(msg) from exc

    @field_validator("mac")
    @classmethod
    def _mac_must_be_bare_hex(cls, value: str | None) -> str | None:
        """Reject anything but a bare 12-hex-char MAC; normalize to lowercase."""
        if value is None:
            return value
        if not _MAC_RE.fullmatch(value):
            msg = (
                "Bulb mac must be 12 hex characters with no separators "
                f"(e.g. 'a8bb5006033d'), got {value!r}"
            )
            raise ValueError(msg)
        # pywizlight's get_mac() returns bare hex; lowercase matches readback format.
        return value.lower()


class GroupConfig(BaseModel):
    """Consumer-side group of bulbs from the same inventory."""

    name: Annotated[str, Field(max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]
    members: Annotated[list[str], Field(min_length=1)]


class PowerSourceConfig(BaseModel):
    """A mains circuit (ADR-007) that one or more bulbs sit behind.

    Claims member bulbs through exactly one of ``group`` or ``members``.
    The inventory shape is available now; deriving and publishing a source
    power belief is deferred to the ADR-007 runtime work.
    """

    name: Annotated[
        str,
        Field(
            max_length=64,
            pattern=r"^[A-Za-z0-9_-]+$",
            description=(
                "Unique power-source name used by bulb power_source references."
            ),
        ),
    ]
    group: str | None = Field(
        default=None,
        description="Name of an existing [[groups]] entry this source powers.",
    )
    members: list[str] | None = Field(
        default=None,
        description=(
            "Bulb names powered by this source. Exactly one of 'group' or "
            "'members' must be set."
        ),
    )
    signal_topic: str | None = Field(
        default=None,
        description=(
            "Retained MQTT topic carrying the raw relay signal "
            "('on' or 'off') for this circuit. wiz2mqtt subscribes to it "
            "and never publishes there."
        ),
    )
    when_unreachable: Literal["fault", "no_power"] = Field(
        default="fault",
        description=(
            "What an unreachable member bulb means with no better evidence: "
            "'fault' (default, availability = offline) or 'no_power'."
        ),
    )
    enable_power_on_request: bool = Field(
        default=False,
        description="Reserve future power-on requests; runtime support is deferred.",
    )
    enable_power_off_request: bool = Field(
        default=False,
        description=(
            "Reserve future power-off requests; runtime support is deferred. "
            "Requires wiz_bulbs_only = true."
        ),
    )
    power_off_idle_delay: float = Field(
        default=600.0,
        description=(
            "Reserved seconds every member bulb must be idle before a future "
            "power-off request; runtime support is deferred."
        ),
    )
    wiz_bulbs_only: bool = Field(
        default=False,
        description=(
            "Operator declaration that every device on this circuit is a "
            "WiZ bulb wiz2mqtt controls. Must be true before "
            "enable_power_off_request may be true."
        ),
    )

    @field_validator("members")
    @classmethod
    def _members_non_empty(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) == 0:
            raise ValueError("Power source members must not be empty when set")
        return value

    @field_validator("signal_topic")
    @classmethod
    def _signal_topic_must_be_valid(cls, value: str | None) -> str | None:
        """Validate like cosalette's topic_prefix check, but non-empty."""
        if value is None:
            return value
        value = value.strip("/")
        if value == "":
            raise ValueError("signal_topic must not be empty")
        for wildcard in ("+", "#"):
            if wildcard in value:
                raise ValueError(
                    f"signal_topic must not contain MQTT wildcard {wildcard!r}"
                )
        if not _SIGNAL_TOPIC_RE.fullmatch(value):
            raise ValueError(
                "signal_topic may only contain letters, digits, and "
                f"'_-./:' (got {value!r})"
            )
        return value


def _index_sources_by_name(
    power_sources: list[Any],
) -> dict[object, list[dict[str, Any]]]:
    """Group the raw ``power_sources`` dicts by their ``name`` value."""
    indexed: dict[object, list[dict[str, Any]]] = {}
    for source in power_sources:
        if isinstance(source, dict):
            typed = cast(dict[str, Any], source)
            indexed.setdefault(typed.get("name"), []).append(typed)
    return indexed


def _is_compatible_no_power_source(source: dict[str, Any], bulb_name: object) -> bool:
    """Whether *source* already is the single-bulb ``no_power`` mapping."""
    return (
        source.get("members") == [bulb_name]
        and source.get("group") is None
        and source.get("when_unreachable", "fault") == "no_power"
    )


def _migrate_legacy_off(
    bulb_name: object,
    power_sources: list[Any],
    sources_by_name: dict[object, list[dict[str, Any]]],
) -> None:
    """Append the implicit single-bulb power source for a legacy ``"off"``."""
    source_name = f"{bulb_name}-power"
    if isinstance(bulb_name, str) and len(source_name) > 64:
        raise ValueError(
            f"Bulb {bulb_name}: cannot migrate legacy "
            "when_unreachable = 'off' because its generated power "
            f"source name {source_name!r} exceeds 64 characters; "
            "declare a shorter compatible [[power_sources]] entry "
            "and remove the legacy key."
        )
    colliding_sources = sources_by_name.get(source_name, [])
    if not colliding_sources:
        implicit_source: dict[str, Any] = {
            "name": source_name,
            "members": [bulb_name],
            "when_unreachable": "no_power",
        }
        power_sources.append(implicit_source)
        sources_by_name[source_name] = [implicit_source]
    elif not all(
        _is_compatible_no_power_source(source, bulb_name)
        for source in colliding_sources
    ):
        raise ValueError(
            f"Bulb {bulb_name}: cannot migrate legacy "
            "when_unreachable = 'off' because the existing "
            f"power source {source_name!r} is not a compatible "
            "single-bulb no_power mapping; remove the legacy key "
            "and resolve the configuration explicitly."
        )
    logger.warning(
        "Bulb %s: when_unreachable = 'off' is replaced by "
        "power_source = %r (see [[power_sources]] name = %r, "
        "when_unreachable = 'no_power'); update wiz2mqtt.toml",
        bulb_name,
        source_name,
        source_name,
    )


def _migrate_legacy_bulb(
    bulb: Any,
    power_sources: list[Any],
    sources_by_name: dict[object, list[dict[str, Any]]],
) -> Any:
    """Return *bulb* without its removed ``when_unreachable`` key, migrated."""
    if not isinstance(bulb, dict) or "when_unreachable" not in bulb:
        return bulb

    bulb = dict(bulb)
    legacy_value = bulb.pop("when_unreachable")
    bulb_name = bulb.get("name", "<unnamed>")

    if legacy_value == "unavailable":
        logger.warning(
            "Bulb %s: when_unreachable = 'unavailable' is now the "
            "implicit default and is no longer a bulb field; remove "
            "it from wiz2mqtt.toml",
            bulb_name,
        )
    elif legacy_value == "off":
        _migrate_legacy_off(bulb_name, power_sources, sources_by_name)
    else:
        raise ValueError(
            f"Bulb {bulb_name}: unsupported legacy when_unreachable "
            f"value {legacy_value!r}. Valid legacy values are 'off' "
            "and 'unavailable'; migrate to a [[power_sources]] entry."
        )
    return bulb


def _check_source_names(
    source: PowerSourceConfig,
    source_names: set[str],
    signal_topics: dict[str, str],
    reserved_names: set[str],
) -> None:
    """Reject a colliding source name or a ``signal_topic`` shared with another."""
    if source.name in source_names or source.name in reserved_names:
        raise ValueError(f"Power source name collides with another name: {source.name}")
    source_names.add(source.name)

    if source.signal_topic is None:
        return
    if previous_source := signal_topics.get(source.signal_topic):
        raise ValueError(
            f"Power sources {previous_source!r} and {source.name!r} "
            "share signal_topic "
            f"{source.signal_topic!r}"
        )
    signal_topics[source.signal_topic] = source.name


def _check_signal_topic_outside_prefix(source: PowerSourceConfig, prefix: str) -> None:
    """Reject a ``signal_topic`` equal to or under wiz2mqtt's own topic prefix.

    cosalette routes external inbound topics before its own command topics, so
    a ``signal_topic`` of ``<prefix>/<bulb>/set`` would take the command topic
    over without any startup error. Compare on segment boundaries so that
    ``wiz2mqtt-relay/x`` stays valid.
    """
    topic = source.signal_topic
    if topic is not None and (topic == prefix or topic.startswith(f"{prefix}/")):
        raise ValueError(
            f"Power source {source.name!r} signal_topic {topic!r} must not be "
            f"the topic prefix {prefix!r} or below it"
        )


def _check_source_members(source: PowerSourceConfig, bulb_names: set[str]) -> None:
    """Reject unknown or duplicate entries in ``source.members``."""
    if source.members is None:
        return
    if unknown := set(source.members) - bulb_names:
        raise ValueError(
            f"Power source {source.name!r} references unknown bulbs: {sorted(unknown)}"
        )
    if len(set(source.members)) != len(source.members):
        raise ValueError(f"Power source {source.name!r} has duplicate members")


def _check_source_claim(
    source: PowerSourceConfig, bulb_names: set[str], group_names: set[str]
) -> None:
    """Validate how *source* selects its bulbs and its power-off request flag."""
    if (source.group is None) == (source.members is None):
        raise ValueError(
            f"Power source {source.name!r} must set exactly one of 'group' or 'members'"
        )
    if source.group is not None and source.group not in group_names:
        raise ValueError(
            f"Power source {source.name!r} references unknown group: {source.group!r}"
        )
    _check_source_members(source, bulb_names)
    if source.enable_power_off_request and not source.wiz_bulbs_only:
        raise ValueError(
            f"Power source {source.name!r}: enable_power_off_request "
            "requires wiz_bulbs_only = true"
        )


def _claimed_bulbs(
    source: PowerSourceConfig, group_members: dict[str, set[str]]
) -> set[str]:
    """Bulb names *source* claims through ``members`` and/or ``group``."""
    claimed: set[str] = set(source.members or [])
    if source.group is not None:
        claimed |= group_members.get(source.group, set())
    return claimed


def _check_bulb_power_sources(
    bulbs: list[BulbConfig],
    power_sources: list[PowerSourceConfig],
    group_members: dict[str, set[str]],
) -> None:
    """Reject an unknown ``power_source`` key or an ambiguous implicit claim."""
    source_names = {source.name for source in power_sources}
    for bulb in bulbs:
        if bulb.power_source is not None and bulb.power_source not in source_names:
            raise ValueError(
                f"Bulb {bulb.name!r} references unknown power_source: "
                f"{bulb.power_source!r}"
            )

    implicit_claims: dict[str, set[str]] = {}
    for source in power_sources:
        for bulb_name in _claimed_bulbs(source, group_members):
            implicit_claims.setdefault(bulb_name, set()).add(source.name)

    for bulb in bulbs:
        claiming_sources = implicit_claims.get(bulb.name, set())
        if bulb.power_source is None and len(claiming_sources) > 1:
            raise ValueError(
                f"Bulb {bulb.name!r} is claimed by multiple power "
                f"sources: {sorted(claiming_sources)}"
            )


def _resolve_power_source(
    bulb: BulbConfig,
    power_sources: list[PowerSourceConfig],
    group_members: dict[str, set[str]],
) -> PowerSourceConfig | None:
    """The bulb's own ``power_source`` wins; else the first source claiming it."""
    if bulb.power_source is not None:
        return next(s for s in power_sources if s.name == bulb.power_source)
    return next(
        (s for s in power_sources if bulb.name in _claimed_bulbs(s, group_members)),
        None,
    )


def _check_power_sources(
    settings: Wiz2MqttSettings, group_members: dict[str, set[str]]
) -> None:
    """Reject a colliding, misplaced or ambiguous ``[[power_sources]]`` entry."""
    bulb_names = {bulb.name for bulb in settings.bulbs}
    group_names = {group.name for group in settings.groups}
    reserved_names = bulb_names | group_names
    prefix = settings.mqtt.topic_prefix or _APP_NAME
    source_names: set[str] = set()
    signal_topics: dict[str, str] = {}
    for source in settings.power_sources:
        _check_source_names(source, source_names, signal_topics, reserved_names)
        _check_signal_topic_outside_prefix(source, prefix)
        _check_source_claim(source, bulb_names, group_names)
    _check_bulb_power_sources(settings.bulbs, settings.power_sources, group_members)


def _members_by_power_source(
    bulbs: list[BulbConfig],
    power_sources: list[PowerSourceConfig],
    resolved: dict[str, PowerSourceConfig | None],
) -> dict[str, tuple[str, ...]]:
    """Reverse *resolved* into the sorted member names of each source."""
    members: dict[str, list[str]] = {source.name: [] for source in power_sources}
    for bulb in bulbs:
        source = resolved[bulb.name]
        if source is not None:
            members[source.name].append(bulb.name)
    return {name: tuple(sorted(names)) for name, names in members.items()}


class Wiz2MqttSettings(cosalette.Settings):
    """wiz2mqtt application settings."""

    model_config = SettingsConfigDict(
        env_prefix="WIZ2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        # config_file is a cosalette runtime convention read via
        # model_config.get("config_file") — pydantic_settings' own
        # SettingsConfigDict TypedDict doesn't declare this key.
        config_file="wiz2mqtt.toml",  # type: ignore
        # Safe to tighten from the base Settings' extra="ignore": env_prefix
        # is set, so only WIZ2MQTT_* env vars are ever seen. This also rejects
        # any TOML top-level key that is not a declared settings field.
        extra="forbid",
    )

    bulbs: list[BulbConfig] = Field(
        default_factory=list,
        description="WiZ bulb inventory, normally supplied via wiz2mqtt.toml.",
    )
    groups: list[GroupConfig] = Field(default_factory=list)
    power_sources: list[PowerSourceConfig] = Field(
        default_factory=list,
        description=(
            "Mains power source (circuit) inventory, normally supplied via "
            "wiz2mqtt.toml (ADR-007)."
        ),
    )
    queued_command_ttl: float = Field(
        default=86400.0,
        description=(
            "In-memory one-slot command queue TTL in seconds (ADR-008). The TTL "
            "takes effect when later replay or restore consumes a queued command."
        ),
    )
    _power_sources_by_bulb: dict[str, PowerSourceConfig | None] = PrivateAttr(
        default_factory=dict
    )
    _members_by_power_source: dict[str, tuple[str, ...]] = PrivateAttr(
        default_factory=dict
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_when_unreachable(cls, data: Any) -> Any:
        """Map the removed bulb-level ``when_unreachable`` to power sources.

        ``extra="forbid"`` would otherwise turn a stale bulb-level key into a
        hard ``ValidationError`` at startup. ``"off"`` becomes an implicit
        single-bulb power source; ``"unavailable"`` (the old default) is
        simply dropped. Both log a warning. Any other legacy value still
        errors, as before (ADR-007, ADR-003 amendment 2026-09-13/2026-09-14).
        """
        if not isinstance(data, dict):
            return data
        bulbs = data.get("bulbs")
        if not isinstance(bulbs, list):
            return data

        raw_sources = data.get("power_sources")
        power_sources = list(raw_sources) if isinstance(raw_sources, list) else []
        sources_by_name = _index_sources_by_name(power_sources)
        migrated_bulbs = [
            _migrate_legacy_bulb(bulb, power_sources, sources_by_name) for bulb in bulbs
        ]

        data = dict(data)
        data["bulbs"] = migrated_bulbs
        data["power_sources"] = power_sources
        return data

    @model_validator(mode="after")
    def _groups_valid(self) -> Wiz2MqttSettings:
        bulb_names = {bulb.name for bulb in self.bulbs}
        group_names: set[str] = set()
        for group in self.groups:
            if group.name in group_names or group.name in bulb_names:
                raise ValueError(f"Group name collides with another name: {group.name}")
            group_names.add(group.name)
            if unknown := set(group.members) - bulb_names:
                raise ValueError(
                    f"Unknown members in group {group.name}: {sorted(unknown)}"
                )
            if len(set(group.members)) != len(group.members):
                raise ValueError(f"Duplicate members in group {group.name}")
        return self

    @model_validator(mode="after")
    def _bulbs_unique(self) -> Wiz2MqttSettings:
        def _dupes(seq: list[str]) -> list[str]:
            return sorted(v for v, c in Counter(seq).items() if c > 1)

        if name_dupes := _dupes([b.name for b in self.bulbs]):
            raise ValueError(f"Bulb names must be unique, duplicates: {name_dupes}")
        if ip_dupes := _dupes([b.ip for b in self.bulbs]):
            raise ValueError(
                f"Bulb ip addresses must be unique, duplicates: {ip_dupes}"
            )
        macs = [b.mac for b in self.bulbs if b.mac is not None]
        if mac_dupes := _dupes(macs):
            raise ValueError(
                f"Bulb mac addresses must be unique, duplicates: {mac_dupes}"
            )
        return self

    @model_validator(mode="after")
    def _power_sources_valid(self) -> Wiz2MqttSettings:
        """Validate [[power_sources]] and the per-bulb power keys (ADR-007).

        Mirrors the shape of :meth:`_groups_valid`. A bulb resolves to at
        most one power source: its own ``power_source`` field wins outright
        (ADR-007 amendment 2026-09-14); otherwise a source claiming the bulb
        through ``members`` or through the bulb's ``group`` claims it, and an
        ambiguous implicit claim (two sources, by members and/or group) is
        an error.
        """
        group_members = {group.name: set(group.members) for group in self.groups}
        _check_power_sources(self, group_members)
        self._power_sources_by_bulb = {
            bulb.name: _resolve_power_source(bulb, self.power_sources, group_members)
            for bulb in self.bulbs
        }
        self._members_by_power_source = _members_by_power_source(
            self.bulbs, self.power_sources, self._power_sources_by_bulb
        )
        return self

    def power_source_of(self, bulb_name: str) -> PowerSourceConfig | None:
        """Resolve the power source claiming *bulb_name*, if any (ADR-007).

        Precedence: the bulb's own ``power_source`` field wins; else a
        source naming the bulb directly through ``members``; else a source
        naming the bulb's group through ``group``. Assumes
        :meth:`_power_sources_valid` already accepted this configuration.
        """
        return self._power_sources_by_bulb.get(bulb_name)

    def bulbs_for_power_source(self, source_name: str) -> list[str]:
        """Return the bulb names resolving to power source *source_name*.

        The reverse of :meth:`power_source_of`: a bulb is a member exactly
        when its own resolution names this source. Sorted for a stable wire
        payload.
        """
        return list(self._members_by_power_source.get(source_name, ()))
