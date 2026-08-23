"""Unit tests for wiz2mqtt settings — Wiz2MqttSettings environment wiring
and the TOML bulb inventory (cap-10u.9).

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

from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings

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

    def test_bulb_when_unreachable_defaults_to_unavailable(self) -> None:
        """Technique: Specification-based."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1")
        assert bulb.when_unreachable == "unavailable"

    def test_bulb_when_unreachable_accepts_off(self) -> None:
        """Technique: Equivalence Partitioning — valid 'off' literal."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1", when_unreachable="off")
        assert bulb.when_unreachable == "off"

    def test_bulb_when_unreachable_rejects_invalid_literal(self) -> None:
        """Technique: Equivalence Partitioning — invalid literal class."""
        with pytest.raises(ValidationError):
            BulbConfig(name="desk", ip="10.0.0.1", when_unreachable="always")  # type: ignore[arg-type]

    def test_bulb_mac_defaults_to_none(self) -> None:
        """Technique: Specification-based — mac is optional identity verification."""
        bulb = BulbConfig(name="desk", ip="10.0.0.1")
        assert bulb.mac is None


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
            when_unreachable = "off"
            """
        )

        settings = Wiz2MqttSettings(_env_file=None, _config_file=str(toml_file))

        assert [b.name for b in settings.bulbs] == ["desk", "lamp"]
        assert settings.bulbs[1].mac == "a8bb5006033d"
        assert settings.bulbs[1].when_unreachable == "off"
        assert settings.bulbs[0].when_unreachable == "unavailable"

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
