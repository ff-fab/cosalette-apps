"""Application settings for wiz2mqtt.

Extends cosalette's Settings with the WIZ2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or a TOML
config file (bulb inventory only). Priority: CLI > env > .env >
wiz2mqtt.toml > defaults.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from typing import Annotated, Literal

import cosalette
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")
_MAC_RE = re.compile(r"[0-9A-Fa-f]{12}")


class BulbConfig(BaseModel):
    """Configuration for a single WiZ bulb.

    ``ip`` is the bulb's identity; ``mac``, when given, is used to verify
    that identity against the bulb's own reported MAC on first contact.
    """

    # Mirrors jeelink2mqtt's name validator; keep in sync until a shared utility exists.
    name: Annotated[str, Field(max_length=64)]
    ip: str
    mac: str | None = None
    when_unreachable: Literal["unavailable", "off"] = "unavailable"

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


class _MqttSettings(cosalette.MqttSettings):
    """MQTT settings pinned to the pre-0.7.0 ``tls=False`` default.

    cosalette 0.7.0 flipped ``MqttSettings.tls`` to ``True`` (ADR-062,
    F-CU1). Redeclaring the field here preserves this app's existing
    runtime behaviour, so upgrading never silently starts a TLS handshake
    the broker cannot answer. Deployments opt in per environment with
    ``WIZ2MQTT_MQTT__TLS=true``.

    A ``default_factory`` only works here because ``mqtt`` is annotated as this
    subclass with ``tls=False`` overridden. If the field stayed typed as the
    base ``MqttSettings``, sibling ``MQTT__*`` variables would restore
    ``tls=True`` during nested-model reconstruction.
    """

    tls: bool = False


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
        # any TOML top-level key that is not a declared field — the config-file
        # source merges the whole parsed file the same way env vars merge. The
        # legal set is exactly this model's fields: "bulbs" and the overridden
        # "mqtt", plus "logging" and "schema_" inherited from cosalette.Settings.
        # Adding a new top-level TOML table therefore means adding a field here
        # (this is the real blocker behind cap-fux's [[groups]], not any
        # framework-side validator).
        extra="forbid",
    )

    mqtt: _MqttSettings = Field(default_factory=_MqttSettings)

    bulbs: list[BulbConfig] = Field(
        default_factory=list,
        description="WiZ bulb inventory, normally supplied via wiz2mqtt.toml.",
    )

    @model_validator(mode="after")
    def _bulbs_unique(self) -> Wiz2MqttSettings:
        def _dupes(seq: list[str]) -> set[str]:
            return {v for v, c in Counter(seq).items() if c > 1}

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
