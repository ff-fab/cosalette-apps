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

    # -- Per-domain polling interval defaults (ADR-005) --

    def test_config_polling_outdoor_default(self, settings: Vito2MqttSettings) -> None:
        """Default outdoor polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_outdoor == 300.0

    def test_config_polling_hot_water_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default hot water polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_hot_water == 300.0

    def test_config_polling_burner_default(self, settings: Vito2MqttSettings) -> None:
        """Default burner polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_burner == 300.0

    def test_config_polling_heating_radiator_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default radiator heating polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_heating_radiator == 300.0

    def test_config_polling_heating_floor_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default floor heating polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_heating_floor == 300.0

    def test_config_polling_system_default(self, settings: Vito2MqttSettings) -> None:
        """Default system polling interval is 3600 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_system == 3600.0

    def test_config_polling_diagnosis_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default diagnosis polling interval is 300 s.

        Technique: Specification-based — ADR-005 per-domain polling.
        """
        assert settings.polling_diagnosis == 300.0

    # -- Legionella treatment defaults --

    def test_config_legionella_temperature_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default legionella temperature is 68 °C.

        Technique: Specification-based — safe default for thermal disinfection.
        """
        assert settings.legionella_temperature == 68

    def test_config_legionella_duration_minutes_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default legionella duration is 40 minutes.

        Technique: Specification-based — standard treatment duration.
        """
        assert settings.legionella_duration_minutes == 40

    def test_config_legionella_safety_margin_minutes_default(
        self, settings: Vito2MqttSettings
    ) -> None:
        """Default legionella safety margin is 30 minutes.

        Technique: Specification-based — margin for heating window check.
        """
        assert settings.legionella_safety_margin_minutes == 30


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

    def test_config_custom_polling_intervals(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Polling intervals accept user-supplied values via env vars.

        Technique: Equivalence Partitioning — valid non-default class.
        """
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
        monkeypatch.setenv("VITO2MQTT_POLLING_OUTDOOR", "60.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_HOT_WATER", "120.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_BURNER", "90.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_HEATING_RADIATOR", "150.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_HEATING_FLOOR", "180.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_SYSTEM", "7200.0")
        monkeypatch.setenv("VITO2MQTT_POLLING_DIAGNOSIS", "600.0")

        settings = Vito2MqttSettings()

        assert settings.polling_outdoor == 60.0
        assert settings.polling_hot_water == 120.0
        assert settings.polling_burner == 90.0
        assert settings.polling_heating_radiator == 150.0
        assert settings.polling_heating_floor == 180.0
        assert settings.polling_system == 7200.0
        assert settings.polling_diagnosis == 600.0

    def test_config_custom_legionella_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legionella settings accept user-supplied values via env vars.

        Technique: Equivalence Partitioning — valid non-default class.
        """
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_TEMPERATURE", "75")
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_DURATION_MINUTES", "60")
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES", "15")

        settings = Vito2MqttSettings()

        assert settings.legionella_temperature == 75
        assert settings.legionella_duration_minutes == 60
        assert settings.legionella_safety_margin_minutes == 15


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
# Polling interval validation
# ---------------------------------------------------------------------------


class TestPollingIntervalValidation:
    """Polling intervals must be positive (gt=0)."""

    @pytest.fixture()
    def _base_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set required env var so only the polling field under test fails."""
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")

    @pytest.mark.usefixtures("_base_env")
    @pytest.mark.parametrize(
        "env_var",
        [
            "VITO2MQTT_POLLING_OUTDOOR",
            "VITO2MQTT_POLLING_HOT_WATER",
            "VITO2MQTT_POLLING_BURNER",
            "VITO2MQTT_POLLING_HEATING_RADIATOR",
            "VITO2MQTT_POLLING_HEATING_FLOOR",
            "VITO2MQTT_POLLING_SYSTEM",
            "VITO2MQTT_POLLING_DIAGNOSIS",
        ],
    )
    def test_config_zero_polling_interval_raises(
        self, monkeypatch: pytest.MonkeyPatch, env_var: str
    ) -> None:
        """A polling interval of 0 must be rejected (gt=0).

        Technique: Error Guessing — boundary value zero.
        """
        monkeypatch.setenv(env_var, "0")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    @pytest.mark.parametrize(
        "env_var",
        [
            "VITO2MQTT_POLLING_OUTDOOR",
            "VITO2MQTT_POLLING_HOT_WATER",
            "VITO2MQTT_POLLING_BURNER",
            "VITO2MQTT_POLLING_HEATING_RADIATOR",
            "VITO2MQTT_POLLING_HEATING_FLOOR",
            "VITO2MQTT_POLLING_SYSTEM",
            "VITO2MQTT_POLLING_DIAGNOSIS",
        ],
    )
    def test_config_negative_polling_interval_raises(
        self, monkeypatch: pytest.MonkeyPatch, env_var: str
    ) -> None:
        """A negative polling interval must be rejected (gt=0).

        Technique: Error Guessing — invalid negative value.
        """
        monkeypatch.setenv(env_var, "-10")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()


# ---------------------------------------------------------------------------
# Legionella validation
# ---------------------------------------------------------------------------


class TestLegionellaValidation:
    """Legionella settings validation."""

    @pytest.fixture()
    def _base_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Set required env var so only the legionella field under test fails."""
        monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")

    @pytest.mark.usefixtures("_base_env")
    def test_config_zero_legionella_temperature_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legionella temperature of 0 must be rejected (gt=0).

        Technique: Error Guessing — boundary value zero.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_TEMPERATURE", "0")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    def test_config_zero_legionella_duration_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legionella duration of 0 must be rejected (gt=0).

        Technique: Error Guessing — boundary value zero.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_DURATION_MINUTES", "0")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    def test_config_negative_legionella_temperature_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative legionella temperature must be rejected (gt=0).

        Technique: Error Guessing — invalid negative value.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_TEMPERATURE", "-10")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    def test_config_negative_legionella_duration_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative legionella duration must be rejected (gt=0).

        Technique: Error Guessing — invalid negative value.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_DURATION_MINUTES", "-10")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    def test_config_negative_legionella_safety_margin_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative legionella safety margin must be rejected (ge=0).

        Technique: Error Guessing — invalid negative value.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES", "-1")
        with pytest.raises(ValidationError):
            Vito2MqttSettings()

    @pytest.mark.usefixtures("_base_env")
    def test_config_zero_legionella_safety_margin_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legionella safety margin of 0 must be accepted (ge=0).

        Technique: Boundary Value Analysis — zero is valid for ge=0.
        """
        monkeypatch.setenv("VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES", "0")
        settings = Vito2MqttSettings()
        assert settings.legionella_safety_margin_minutes == 0


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
