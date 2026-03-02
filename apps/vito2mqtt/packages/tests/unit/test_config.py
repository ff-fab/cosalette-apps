# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for config.py — Vito2MqttSettings.

Test Techniques Used:
- Specification-based: Verify required/optional fields and defaults
- Error Guessing: Missing required fields, invalid enum values
- Equivalence Partitioning: Valid/invalid signal_language values
- Environment Variable Testing: monkeypatch.setenv for env-based construction
"""

from __future__ import annotations

import pytest
from cosalette import Settings
from pydantic import ValidationError

from vito2mqtt.config import Vito2MqttSettings

# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


class TestInheritance:
    """Vito2MqttSettings inherits from cosalette.Settings."""

    def test_settings_is_subclass_of_cosalette_settings(self) -> None:
        """Vito2MqttSettings must extend cosalette.Settings.

        Technique: Specification-based — architecture requires cosalette base.
        """
        assert issubclass(Vito2MqttSettings, Settings)


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


class TestRequiredFields:
    """serial_port is the only required field."""

    def test_config_serial_port_required_raises_without_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructing without serial_port must raise ValidationError.

        Technique: Error Guessing — missing mandatory field.
        """
        # Ensure no env var leaks in
        monkeypatch.delenv("VITO2MQTT_SERIAL_PORT", raising=False)
        with pytest.raises(ValidationError):
            Vito2MqttSettings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


class TestDefaults:
    """Verify default values for optional fields."""

    @pytest.fixture()
    def settings(self, monkeypatch: pytest.MonkeyPatch) -> Vito2MqttSettings:
        """Construct settings with only the required field."""
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
        return Vito2MqttSettings()

    def test_config_serial_baud_rate_default(self, settings: Vito2MqttSettings) -> None:
        """Default baud rate is 4800 (Optolink standard).

        Technique: Specification-based — P300 protocol requires 4800 baud.
        """
        assert settings.serial_baud_rate == 4800

    def test_config_device_id_default(self, settings: Vito2MqttSettings) -> None:
        """Default device_id is 'vitodens200w'.

        Technique: Specification-based — project default device.
        """
        assert settings.device_id == "vitodens200w"

    def test_config_signal_language_default(self, settings: Vito2MqttSettings) -> None:
        """Default signal_language is 'en' per ADR-006.

        Technique: Specification-based — ADR-006 default language.
        """
        assert settings.signal_language == "en"


# ---------------------------------------------------------------------------
# Custom values
# ---------------------------------------------------------------------------


class TestCustomValues:
    """Custom values override defaults."""

    def test_config_custom_values_override_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All fields accept user-supplied values.

        Technique: Equivalence Partitioning — valid non-default class.
        """
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyS1")
        monkeypatch.setenv("VITO2MQTT_SERIAL_BAUD_RATE", "9600")
        monkeypatch.setenv("VITO2MQTT_DEVICE_ID", "vitotronic300")
        monkeypatch.setenv("VITO2MQTT_SIGNAL_LANGUAGE", "de")

        settings = Vito2MqttSettings()

        assert settings.serial_port == "/dev/ttyS1"
        assert settings.serial_baud_rate == 9600
        assert settings.device_id == "vitotronic300"
        assert settings.signal_language == "de"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """Pydantic validation catches invalid inputs."""

    def test_config_invalid_signal_language_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """signal_language must be 'de' or 'en'.

        Technique: Error Guessing — invalid Literal value.
        """
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
        monkeypatch.setenv("VITO2MQTT_SIGNAL_LANGUAGE", "fr")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()


# ---------------------------------------------------------------------------
# Environment prefix
# ---------------------------------------------------------------------------


class TestEnvPrefix:
    """Environment variables use the VITO2MQTT_ prefix."""

    def test_config_env_prefix_is_vito2mqtt(self) -> None:
        """model_config must define env_prefix='VITO2MQTT_'.

        Technique: Specification-based — ensures env isolation.
        """
        assert Vito2MqttSettings.model_config.get("env_prefix") == "VITO2MQTT_"

    def test_config_serial_port_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """serial_port is populated from VITO2MQTT_SERIAL_PORT env var.

        Technique: Specification-based — env-based construction.
        """
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyACM0")
        settings = Vito2MqttSettings()
        assert settings.serial_port == "/dev/ttyACM0"
