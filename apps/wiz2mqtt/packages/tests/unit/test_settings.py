"""Unit tests for wiz2mqtt settings — Wiz2MqttSettings environment wiring
and the TOML bulb inventory .

Test Techniques Used:
- Specification-based: Default values match cosalette's base Settings
- Error Guessing: The WIZ2MQTT_ prefix must actually be honored — a prior
  scaffold gap left the app instantiating the base Settings class with no
  prefix, so app.run()'s dependents (e.g. compose.yml's
  WIZ2MQTT_MQTT__HOST) were silently ignored.
- Equivalence Partitioning: valid/invalid name, ip, mac, and when_unreachable values
- Boundary Value Analysis: mac hex-length boundary
- Decision Table: bulb uniqueness across name/ip/mac, including mixed mac presence
- Round-trip Testing: a real TOML file loaded end-to-end via _config_file
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cosalette import SettingsLoadError
from pydantic import ValidationError

from wiz2mqtt.settings import (
    BulbConfig,
    GroupConfig,
    PowerSourceConfig,
    Wiz2MqttSettings,
)

_UNCONFIGURED = {"_env_file": None, "_config_file": None}
"""Kwargs isolating a Wiz2MqttSettings() call from any real .env/.toml on disk."""


@pytest.mark.unit
class TestWiz2MqttSettings:
    """Verify the WIZ2MQTT_ environment prefix is wired and honored."""

    def test_default_mqtt_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no env vars set, MQTT host falls back to cosalette's default."""
        monkeypatch.delenv("WIZ2MQTT_MQTT__HOST", raising=False)
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_mqtt_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WIZ2MQTT_MQTT__HOST must be honored — the wiring compose.yml relies on."""
        monkeypatch.setenv("WIZ2MQTT_MQTT__HOST", "mosquitto")
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.mqtt.host == "mosquitto"

    def test_unprefixed_env_var_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare MQTT__HOST (no WIZ2MQTT_ prefix) must NOT be picked up."""
        monkeypatch.setenv("MQTT__HOST", "should-not-apply")
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_logging_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WIZ2MQTT_LOGGING__LEVEL must be honored."""
        monkeypatch.setenv("WIZ2MQTT_LOGGING__LEVEL", "DEBUG")
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.logging.level == "DEBUG"

    def test_default_bulbs_is_empty(self) -> None:
        """An empty inventory is valid — not every deployment configures bulbs."""
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.bulbs == []


# ---------------------------------------------------------------------------
# BulbConfig field validation
# ---------------------------------------------------------------------------


class TestBulbConfigDefaults:
    """Optional BulbConfig fields default sensibly."""

    def test_bulb_mac_defaults_to_none(self) -> None:
        """Technique: Specification-based — mac is optional identity verification."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1")
        assert bulb.mac is None

    def test_bulb_power_source_defaults_to_none(self) -> None:
        """Technique: Specification-based."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1")
        assert bulb.power_source is None

    def test_bulb_restore_previous_state_defaults_to_false(self) -> None:
        """Technique: Specification-based."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1")
        assert bulb.restore_previous_state is False


class TestBulbNameValidation:
    """Bulb names must be valid MQTT topic segments."""

    @pytest.mark.parametrize(
        "name",
        ["office", "outdoor", "living-room", "sensor_1", "Sensor-A1", "abc123"],
    )
    def test_bulb_name_accepts_valid_topic_segments(self, name: str) -> None:
        """Technique: Equivalence Partitioning — valid-name class."""
        bulb = BulbConfig(name=name, ip="10.0.0.1")
        assert bulb.name == name

    @pytest.mark.parametrize(
        "name",
        ["", "office/room", "sensor+1", "sensor#1", "sensor name", "sensor\tid"],
    )
    def test_bulb_name_rejects_invalid_topic_segments(self, name: str) -> None:
        """Technique: Equivalence Partitioning — invalid-name class."""
        with pytest.raises(ValidationError, match="name"):
            BulbConfig(name=name, ip="10.0.0.1")


class TestBulbIpValidation:
    """Bulb ip must be a literal IPv4 address — it is the bulb's identity."""

    @pytest.mark.parametrize("ip", ["10.0.0.1", "192.168.1.255", "0.0.0.0"])
    def test_bulb_ip_accepts_valid_ipv4(self, ip: str) -> None:
        """Technique: Equivalence Partitioning — valid IPv4 class."""
        bulb = BulbConfig(name="desk", ip=ip)
        assert bulb.ip == ip

    @pytest.mark.parametrize(
        "ip", ["not-an-ip", "bulb.local", "10.0.0.256", "10.0.0", ""]
    )
    def test_bulb_ip_rejects_invalid_values(self, ip: str) -> None:
        """Technique: Equivalence Partitioning — invalid-ip class."""
        with pytest.raises(ValidationError, match="ip"):
            BulbConfig(name="desk", ip=ip)


class TestBulbMacValidation:
    """Bulb mac, when given, must match pywizlight's bare-hex readback format."""

    @pytest.mark.parametrize(
        ("mac", "expected"),
        [
            ("a8bb5006033d", "a8bb5006033d"),
            ("A8BB5006033D", "a8bb5006033d"),  # normalized to lowercase
        ],
    )
    def test_bulb_mac_accepts_and_normalizes_bare_hex(
        self, mac: str, expected: str
    ) -> None:
        """Technique: Equivalence Partitioning + Specification-based normalization."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1", mac=mac)
        assert bulb.mac == expected

    @pytest.mark.parametrize(
        "mac",
        [
            "a8:bb:50:06:03:3d",  # colons rejected — not the readback format
            "a8bb5006033",  # 11 chars — boundary value analysis
            "a8bb5006033dd",  # 13 chars — boundary value analysis
            "zzbb5006033d",  # non-hex chars
        ],
    )
    def test_bulb_mac_rejects_non_bare_hex(self, mac: str) -> None:
        """Technique: Boundary Value Analysis — 12-char hex-string boundary."""
        with pytest.raises(ValidationError, match="mac"):
            BulbConfig(name="desk", ip="10.0.0.1", mac=mac)


# ---------------------------------------------------------------------------
# Root-settings uniqueness validators
# ---------------------------------------------------------------------------


class TestBulbsUniqueness:
    """Duplicate identity within the bulb inventory is rejected."""

    def test_bulbs_reject_duplicate_names(self) -> None:
        """Technique: Decision Table — name collision."""
        with pytest.raises(ValidationError, match="name"):
            Wiz2MqttSettings(
                bulbs=[
                    {"name": "desk", "ip": "10.0.0.1"},
                    {"name": "desk", "ip": "10.0.0.2"},
                ],
                **_UNCONFIGURED,
            )

    def test_bulbs_reject_duplicate_ips(self) -> None:
        """Technique: Decision Table — ip collision."""
        with pytest.raises(ValidationError, match="ip"):
            Wiz2MqttSettings(
                bulbs=[
                    {"name": "desk", "ip": "10.0.0.1"},
                    {"name": "lamp", "ip": "10.0.0.1"},
                ],
                **_UNCONFIGURED,
            )

    def test_bulbs_reject_duplicate_macs(self) -> None:
        """Technique: Decision Table — mac collision."""
        with pytest.raises(ValidationError, match="mac"):
            Wiz2MqttSettings(
                bulbs=[
                    {"name": "desk", "ip": "10.0.0.1", "mac": "a8bb5006033d"},
                    {"name": "lamp", "ip": "10.0.0.2", "mac": "a8bb5006033d"},
                ],
                **_UNCONFIGURED,
            )

    def test_bulbs_allow_multiple_bulbs_without_mac(self) -> None:
        """None macs must not collide with each other.

        Technique: Decision Table — absent-mac equivalence class.
        """
        settings = Wiz2MqttSettings(
            bulbs=[
                {"name": "desk", "ip": "10.0.0.1"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            **_UNCONFIGURED,
        )
        assert len(settings.bulbs) == 2

    def test_bulbs_allow_mixed_mac_presence(self) -> None:
        """One bulb with mac, one without must not raise a false duplicate alarm.

        Technique: Decision Table — absent-mac + present-mac equivalence classes.
        """
        settings = Wiz2MqttSettings(
            bulbs=[
                {"name": "desk", "ip": "10.0.0.1", "mac": "a8bb5006033d"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            **_UNCONFIGURED,
        )
        assert len(settings.bulbs) == 2


class TestExtraTopLevelKeyRejected:
    """A TOML top-level key other than 'bulbs' is rejected, not silently ignored."""

    def test_settings_rejects_unknown_top_level_toml_key(self, tmp_path: Path) -> None:
        """Technique: Error Guessing — extra="forbid" catches config-file extras too."""
        toml_file = tmp_path / "wiz2mqtt.toml"
        toml_file.write_text('foo = "bar"\nbulbs = []\n')

        with pytest.raises(ValidationError):
            Wiz2MqttSettings(_env_file=None, _config_file=str(toml_file))


# ---------------------------------------------------------------------------
# Config-file loading (first consumer of cosalette's config-file source)
# ---------------------------------------------------------------------------


class TestConfigFileLoading:
    """The bulb inventory loads correctly from a real TOML file on disk."""

    def test_settings_loads_bulbs_from_toml_file(self, tmp_path: Path) -> None:
        """Technique: Round-trip Testing — write TOML, load, compare."""
        toml_file = tmp_path / "wiz2mqtt.toml"
        toml_file.write_text(
            """
            [[bulbs]]
            name = "desk"
            ip = "10.0.0.1"

            [[bulbs]]
            name = "lamp"
            ip = "10.0.0.2"
            mac = "a8bb5006033d"
            """
        )

        settings = Wiz2MqttSettings(_env_file=None, _config_file=str(toml_file))

        assert [b.name for b in settings.bulbs] == ["desk", "lamp"]
        assert settings.bulbs[1].mac == "a8bb5006033d"

    def test_settings_env_overrides_config_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env vars outrank the config file per cosalette's documented precedence.

        Technique: Specification-based — precedence contract.
        """
        toml_file = tmp_path / "wiz2mqtt.toml"
        toml_file.write_text("bulbs = []\n")
        monkeypatch.setenv("WIZ2MQTT_MQTT__HOST", "from-env")

        settings = Wiz2MqttSettings(_env_file=None, _config_file=str(toml_file))

        assert settings.mqtt.host == "from-env"


class TestConfigFileMissing:
    """A configured-but-absent config file fails loudly, not silently."""

    def test_settings_raises_when_config_file_does_not_exist(
        self, tmp_path: Path
    ) -> None:
        """Technique: Error Guessing — fail-loud contract on a missing file."""
        missing = tmp_path / "does-not-exist.toml"

        with pytest.raises(SettingsLoadError):
            Wiz2MqttSettings(_env_file=None, _config_file=str(missing))


class TestGroups:
    """Decision-table validation of consumer group membership."""

    @pytest.mark.parametrize("name", ["", "a/b", "a+b", "a#b", "a b", "x" * 65])
    def test_invalid_names(self, name: str) -> None:
        """Invalid MQTT segments and overlong names fail before rendering."""
        with pytest.raises(ValidationError):
            GroupConfig(name=name, members=["desk"])

    @pytest.mark.parametrize(
        "groups",
        [
            [{"name": "desk", "members": ["desk"]}],
            [{"name": "all", "members": ["missing"]}],
            [{"name": "all", "members": []}],
            [{"name": "all", "members": ["desk", "desk"]}],
            [
                {"name": "all", "members": ["desk"]},
                {"name": "all", "members": ["desk"]},
            ],
        ],
    )
    def test_invalid_membership(self, groups: list[dict[str, object]]) -> None:
        """Reject collisions, unknown members, empty and duplicate membership."""
        with pytest.raises(ValidationError):
            Wiz2MqttSettings(
                bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
                groups=groups,
                **_UNCONFIGURED,
            )

    def test_groups_load_from_toml(self, tmp_path: Path) -> None:
        """Round trip: overlapping groups resolve against the bulb inventory."""
        config = tmp_path / "wiz2mqtt.toml"
        config.write_text(
            '[[bulbs]]\nname="desk"\nip="10.0.0.1"\n'
            '[[groups]]\nname="All-lights"\nmembers=["desk"]\n'
            '[[groups]]\nname="floor_1"\nmembers=["desk"]\n'
        )
        settings = Wiz2MqttSettings(_env_file=None, _config_file=str(config))
        assert [g.members for g in settings.groups] == [["desk"], ["desk"]]
        assert Wiz2MqttSettings(**_UNCONFIGURED).groups == []


# ---------------------------------------------------------------------------
# PowerSourceConfig field validation
# ---------------------------------------------------------------------------


class TestPowerSourceMembersValidation:
    """Technique: Equivalence Partitioning — members presence/emptiness."""

    def test_members_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError, match="members must not be empty"):
            PowerSourceConfig(name="kitchen-power", members=[])

    def test_members_accepts_none(self) -> None:
        source = PowerSourceConfig(name="kitchen-power", group="kitchen")
        assert source.members is None


class TestPowerSourceSignalTopicValidation:
    """Mirrors cosalette's topic_prefix validation; signal_topic is non-empty."""

    @pytest.mark.parametrize(
        "topic", ["openhab/relay/downstairs/state", "relay1", "a/b/c"]
    )
    def test_signal_topic_accepts_valid_topics(self, topic: str) -> None:
        """Technique: Equivalence Partitioning — valid-topic class."""
        source = PowerSourceConfig(name="p", members=["desk"], signal_topic=topic)
        assert source.signal_topic == topic

    def test_signal_topic_strips_leading_trailing_slashes(self) -> None:
        """Technique: Boundary Value Analysis — leading/trailing slash boundary."""
        source = PowerSourceConfig(
            name="p", members=["desk"], signal_topic="/relay/state/"
        )
        assert source.signal_topic == "relay/state"

    @pytest.mark.parametrize("topic", ["", "a/+/b", "a/#", "a b", "a$b"])
    def test_signal_topic_rejects_invalid_topics(self, topic: str) -> None:
        """Technique: Equivalence Partitioning — invalid-topic class (empty,
        wildcards, out-of-charset)."""
        with pytest.raises(ValidationError):
            PowerSourceConfig(name="p", members=["desk"], signal_topic=topic)


# ---------------------------------------------------------------------------
# [[power_sources]] cross-field validation on Wiz2MqttSettings
# ---------------------------------------------------------------------------


class TestPowerSourcesValidation:
    """Decision-table validation mirroring TestGroups, for [[power_sources]]
    (ADR-007, amendment 2026-09-14)."""

    def _settings(self, **overrides: object) -> Wiz2MqttSettings:
        defaults: dict[str, object] = {
            "bulbs": [
                {"name": "desk", "ip": "10.0.0.1"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            "groups": [{"name": "downstairs", "members": ["desk", "lamp"]}],
        }
        return Wiz2MqttSettings(**{**defaults, **overrides}, **_UNCONFIGURED)

    def test_rejects_name_colliding_with_bulb(self) -> None:
        with pytest.raises(ValidationError, match="collides with another name"):
            self._settings(power_sources=[{"name": "desk", "members": ["desk"]}])

    def test_rejects_name_colliding_with_group(self) -> None:
        with pytest.raises(ValidationError, match="collides with another name"):
            self._settings(power_sources=[{"name": "downstairs", "members": ["desk"]}])

    def test_rejects_both_group_and_members_set(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of"):
            self._settings(
                power_sources=[
                    {"name": "p", "group": "downstairs", "members": ["desk"]}
                ]
            )

    def test_rejects_neither_group_nor_members_set(self) -> None:
        with pytest.raises(ValidationError, match="exactly one of"):
            self._settings(power_sources=[{"name": "p"}])

    def test_rejects_unknown_group_reference(self) -> None:
        with pytest.raises(ValidationError, match="unknown group"):
            self._settings(power_sources=[{"name": "p", "group": "upstairs"}])

    def test_rejects_unknown_member_bulb(self) -> None:
        with pytest.raises(ValidationError, match="unknown bulbs"):
            self._settings(power_sources=[{"name": "p", "members": ["missing"]}])

    def test_rejects_duplicate_member_in_members(self) -> None:
        with pytest.raises(ValidationError, match="duplicate members"):
            self._settings(power_sources=[{"name": "p", "members": ["desk", "desk"]}])

    def test_rejects_power_off_without_wiz_bulbs_only(self) -> None:
        with pytest.raises(ValidationError, match="requires wiz_bulbs_only"):
            self._settings(
                power_sources=[
                    {
                        "name": "p",
                        "members": ["desk"],
                        "enable_power_off_request": True,
                    }
                ]
            )

    def test_allows_power_off_with_wiz_bulbs_only(self) -> None:
        settings = self._settings(
            power_sources=[
                {
                    "name": "p",
                    "members": ["desk"],
                    "enable_power_off_request": True,
                    "wiz_bulbs_only": True,
                }
            ]
        )
        assert settings.power_sources[0].enable_power_off_request is True

    def test_rejects_bulb_referencing_unknown_power_source(self) -> None:
        with pytest.raises(ValidationError, match="unknown power_source"):
            self._settings(
                bulbs=[{"name": "desk", "ip": "10.0.0.1", "power_source": "ghost"}],
                groups=[],
            )

    def test_rejects_bulb_double_claimed_by_two_sources_via_members(self) -> None:
        with pytest.raises(ValidationError, match="claimed by multiple power"):
            self._settings(
                power_sources=[
                    {"name": "p1", "members": ["desk"]},
                    {"name": "p2", "members": ["desk"]},
                ]
            )

    def test_rejects_bulb_double_claimed_by_members_and_group(self) -> None:
        with pytest.raises(ValidationError, match="claimed by multiple power"):
            self._settings(
                power_sources=[
                    {"name": "p1", "members": ["desk"]},
                    {"name": "p2", "group": "downstairs"},
                ]
            )

    def test_explicit_power_source_wins_over_group_claim_no_error(self) -> None:
        """ADR-007 amendment: explicit power_source beats an implicit group
        claim with no error, even though the group also claims this bulb."""
        settings = self._settings(
            bulbs=[
                {"name": "desk", "ip": "10.0.0.1", "power_source": "other"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            power_sources=[
                {"name": "p1", "group": "downstairs"},
                {"name": "other", "members": ["desk"]},
            ],
        )
        resolved = settings.power_source_of("desk")
        assert resolved is not None
        assert resolved.name == "other"


# ---------------------------------------------------------------------------
# power_source_of resolution
# ---------------------------------------------------------------------------


class TestPowerSourceOf:
    """Technique: State Transition / Decision Table — resolution precedence."""

    def test_resolves_via_direct_members(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
            power_sources=[{"name": "p", "members": ["desk"]}],
            **_UNCONFIGURED,
        )
        source = settings.power_source_of("desk")
        assert source is not None
        assert source.name == "p"

    def test_resolves_via_group(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
            groups=[{"name": "downstairs", "members": ["desk"]}],
            power_sources=[{"name": "p", "group": "downstairs"}],
            **_UNCONFIGURED,
        )
        source = settings.power_source_of("desk")
        assert source is not None
        assert source.name == "p"

    def test_direct_power_source_wins_over_group(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1", "power_source": "other"}],
            groups=[{"name": "downstairs", "members": ["desk"]}],
            power_sources=[
                {"name": "p", "group": "downstairs"},
                {"name": "other", "members": ["desk"]},
            ],
            **_UNCONFIGURED,
        )
        source = settings.power_source_of("desk")
        assert source is not None
        assert source.name == "other"

    def test_returns_none_when_no_source_claims_bulb(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}], **_UNCONFIGURED
        )
        assert settings.power_source_of("desk") is None

    def test_returns_none_for_unknown_bulb_name(self) -> None:
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.power_source_of("ghost") is None


# ---------------------------------------------------------------------------
# Legacy bulb-level when_unreachable migration
# ---------------------------------------------------------------------------


class TestLegacyWhenUnreachableMigration:
    """Pre-ADR-007 bulb-level when_unreachable migrates to power_sources
    (ADR-003 amendment 2026-09-14 Corrective)."""

    def test_off_creates_implicit_power_source(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Technique: Decision Table — legacy 'off' branch."""
        with caplog.at_level("WARNING"):
            settings = Wiz2MqttSettings(
                bulbs=[{"name": "desk", "ip": "10.0.0.1", "when_unreachable": "off"}],
                **_UNCONFIGURED,
            )

        assert settings.bulbs[0].name == "desk"
        source = settings.power_source_of("desk")
        assert source is not None
        assert source.name == "desk-power"
        assert source.members == ["desk"]
        assert source.when_unreachable == "no_power"
        assert "when_unreachable = 'off'" in caplog.text

    def test_unavailable_drops_key_with_warning_no_source_created(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Technique: Decision Table — legacy 'unavailable' branch (no-op)."""
        with caplog.at_level("WARNING"):
            settings = Wiz2MqttSettings(
                bulbs=[
                    {
                        "name": "desk",
                        "ip": "10.0.0.1",
                        "when_unreachable": "unavailable",
                    }
                ],
                **_UNCONFIGURED,
            )

        assert settings.power_sources == []
        assert settings.power_source_of("desk") is None
        assert "when_unreachable = 'unavailable'" in caplog.text

    def test_unsupported_legacy_value_still_errors(self) -> None:
        """Technique: Equivalence Partitioning — invalid legacy value class."""
        with pytest.raises(ValidationError, match="unsupported legacy"):
            Wiz2MqttSettings(
                bulbs=[
                    {"name": "desk", "ip": "10.0.0.1", "when_unreachable": "always"}
                ],
                **_UNCONFIGURED,
            )


# ---------------------------------------------------------------------------
# queued_command_ttl
# ---------------------------------------------------------------------------


class TestQueuedCommandTtl:
    """Technique: Specification-based."""

    def test_defaults_to_one_day(self) -> None:
        settings = Wiz2MqttSettings(**_UNCONFIGURED)
        assert settings.queued_command_ttl == 86400.0
