"""Unit tests for geiger2mqtt settings — Geiger2MqttSettings environment wiring.

Test Techniques Used:
- Specification-based: Default values match cosalette's base Settings
- Error Guessing: The GEIGER2MQTT_ prefix must actually be honored, and an
  unprefixed var must NOT leak in — env-prefix wiring is easy to get wrong
  silently (a real prior scaffold gap: cap-a8g).
"""

from __future__ import annotations

import pytest

from geiger2mqtt.settings import Geiger2MqttSettings


@pytest.mark.unit
class TestGeiger2MqttSettings:
    """Verify the GEIGER2MQTT_ environment prefix is wired and honored."""

    def test_default_mqtt_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no env vars set, MQTT host falls back to cosalette's default."""
        monkeypatch.delenv("GEIGER2MQTT_MQTT__HOST", raising=False)
        settings = Geiger2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_mqtt_host(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GEIGER2MQTT_MQTT__HOST must be honored — the wiring compose.yml relies on."""
        monkeypatch.setenv("GEIGER2MQTT_MQTT__HOST", "mosquitto")
        settings = Geiger2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "mosquitto"

    def test_unprefixed_env_var_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare MQTT__HOST (no GEIGER2MQTT_ prefix) must NOT be picked up."""
        monkeypatch.setenv("MQTT__HOST", "should-not-apply")
        settings = Geiger2MqttSettings(_env_file=None)
        assert settings.mqtt.host == "localhost"

    def test_prefixed_env_var_overrides_logging_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """GEIGER2MQTT_LOGGING__LEVEL must be honored."""
        monkeypatch.setenv("GEIGER2MQTT_LOGGING__LEVEL", "DEBUG")
        settings = Geiger2MqttSettings(_env_file=None)
        assert settings.logging.level == "DEBUG"
