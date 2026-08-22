"""Unit tests for wiz2mqtt settings — Wiz2MqttSettings environment wiring.

Test Techniques Used:
- Specification-based: Default values match cosalette's base Settings
- Error Guessing: The WIZ2MQTT_ prefix must actually be honored — a prior
  scaffold gap left the app instantiating the base Settings class with no
  prefix, so app.run()'s dependents (e.g. compose.yml's
  WIZ2MQTT_MQTT__HOST) were silently ignored.
"""

from __future__ import annotations

import pytest

from wiz2mqtt.settings import Wiz2MqttSettings


@pytest.mark.unit
class TestWiz2MqttSettings:
    """Verify the WIZ2MQTT_ environment prefix is wired and honored."""

    def test_default_mqtt_host(self) -> None:
        """With no env vars set, MQTT host falls back to cosalette's default."""
        settings = Wiz2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_mqtt_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WIZ2MQTT_MQTT__HOST must be honored — the wiring compose.yml relies on."""
        monkeypatch.setenv("WIZ2MQTT_MQTT__HOST", "mosquitto")
        settings = Wiz2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "mosquitto"

    def test_unprefixed_env_var_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare MQTT__HOST (no WIZ2MQTT_ prefix) must NOT be picked up."""
        monkeypatch.setenv("MQTT__HOST", "should-not-apply")
        settings = Wiz2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_logging_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WIZ2MQTT_LOGGING__LEVEL must be honored."""
        monkeypatch.setenv("WIZ2MQTT_LOGGING__LEVEL", "DEBUG")
        settings = Wiz2MqttSettings(_env_file=None)
        assert settings.logging.level == "DEBUG"
