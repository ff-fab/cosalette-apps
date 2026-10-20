"""Unit tests for geiger2mqtt settings — Geiger2MqttSettings environment wiring.

Test Techniques Used:
- Specification-based: Default values match cosalette's base Settings
  and the documented geiger counter defaults
- Boundary Value Analysis: each validated setting just inside and just
  outside its valid range
- Error Guessing: The GEIGER2MQTT_ prefix must actually be honored, and an
  unprefixed var must NOT leak in — env-prefix wiring is easy to get wrong
  silently (a real prior scaffold gap: cap-a8g).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


@pytest.mark.unit
class TestGeigerDefaults:
    """Documented defaults of the geiger counter settings."""

    def test_defaults(self) -> None:
        """Technique: Specification-based — the epic's settings table."""
        settings = Geiger2MqttSettings(_env_file=None)

        assert settings.gpio_pin == 4
        assert settings.gpio_chip == "/dev/gpiochip0"
        assert settings.gpio_pull_up is False
        assert settings.conversion_factor == 0.0057
        assert settings.average_window == 900.0
        assert settings.publish_interval == 30.0
        assert settings.no_pulse_timeout == 300.0

    def test_env_vars_override_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Technique: Specification-based — every setting reads GEIGER2MQTT_*."""
        env = {
            "GPIO_PIN": "17",
            "GPIO_CHIP": "/dev/gpiochip4",
            "GPIO_PULL_UP": "true",
            "CONVERSION_FACTOR": "0.0081",
            "AVERAGE_WINDOW": "600",
            "PUBLISH_INTERVAL": "10",
            "NO_PULSE_TIMEOUT": "0",
        }
        for key, value in env.items():
            monkeypatch.setenv(f"GEIGER2MQTT_{key}", value)

        settings = Geiger2MqttSettings(_env_file=None)

        assert settings.gpio_pin == 17
        assert settings.gpio_chip == "/dev/gpiochip4"
        assert settings.gpio_pull_up is True
        assert settings.conversion_factor == 0.0081
        assert settings.average_window == 600.0
        assert settings.publish_interval == 10.0
        assert settings.no_pulse_timeout == 0.0


@pytest.mark.unit
class TestGeigerValidation:
    """Boundaries of the validated settings."""

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gpio_chip", "gpiochip0"),
            ("gpio_chip", "/sys/class/gpio"),
            ("conversion_factor", 0),
            ("conversion_factor", -0.0057),
            ("average_window", 59.9),
            ("no_pulse_timeout", -1),
            ("publish_interval", 0),
        ],
    )
    def test_rejects_invalid_values(self, field: str, value: object) -> None:
        """Technique: Boundary Value Analysis — just outside each valid range."""
        with pytest.raises(ValidationError):
            Geiger2MqttSettings(_env_file=None, **{field: value})

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("gpio_chip", "/dev/gpiochip0"),
            ("conversion_factor", 1e-9),
            ("average_window", 60),
            ("no_pulse_timeout", 0),
        ],
    )
    def test_accepts_boundary_values(self, field: str, value: object) -> None:
        """Technique: Boundary Value Analysis — on each valid boundary."""
        settings = Geiger2MqttSettings(_env_file=None, **{field: value})

        assert getattr(settings, field) == value
