"""Unit tests for gas2mqtt settings — Gas2MqttSettings validation.

Test Techniques Used:
- Boundary Value Analysis: Numeric field constraints (ge, gt, le)
- Equivalence Partitioning: Valid/invalid setting values
- Specification-based: Default values match legacy behavior
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_gas2mqtt_settings


@pytest.mark.unit
class TestGas2MqttSettingsDefaults:
    """Verify default values match legacy behavior and documentation."""

    def test_default_i2c_bus(self) -> None:
        """Default I2C bus is 1 (newer Raspberry Pi models)."""
        settings = make_gas2mqtt_settings()
        assert settings.i2c_bus == 1

    def test_default_i2c_address(self) -> None:
        """Default I2C address is 0x0D (QMC5883L)."""
        settings = make_gas2mqtt_settings()
        assert settings.i2c_address == 0x0D

    def test_default_trigger_level(self) -> None:
        """Default trigger level matches legacy constant."""
        settings = make_gas2mqtt_settings()
        assert settings.trigger_level == -5000

    def test_default_trigger_hysteresis(self) -> None:
        """Default hysteresis matches legacy constant."""
        settings = make_gas2mqtt_settings()
        assert settings.trigger_hysteresis == 700

    def test_default_poll_interval(self) -> None:
        """Default poll interval is 1 second (legacy loop rate)."""
        settings = make_gas2mqtt_settings()
        assert settings.poll_interval == 1.0

    def test_default_temperature_interval(self) -> None:
        """Default temperature interval is 300 seconds (5 minutes)."""
        settings = make_gas2mqtt_settings()
        assert settings.temperature_interval == 300.0

    def test_default_temp_calibration(self) -> None:
        """Default calibration matches legacy empirical formula."""
        settings = make_gas2mqtt_settings()
        assert settings.temp_scale == 0.008
        assert settings.temp_offset == 20.3

    def test_default_smoothing_tau(self) -> None:
        """Default smoothing_tau gives alpha=0.2 at dt=300s."""
        settings = make_gas2mqtt_settings()
        assert settings.smoothing_tau == 1200.0

    def test_consumption_tracking_disabled_by_default(self) -> None:
        """Consumption tracking is opt-in."""
        settings = make_gas2mqtt_settings()
        assert settings.enable_consumption_tracking is False

    def test_default_liters_per_tick(self) -> None:
        """Default liters per tick is 10 (0.01 m³)."""
        settings = make_gas2mqtt_settings()
        assert settings.liters_per_tick == 10.0

    def test_debug_device_disabled_by_default(self) -> None:
        """Debug magnetometer device is opt-in."""
        settings = make_gas2mqtt_settings()
        assert settings.enable_debug_device is False


@pytest.mark.unit
class TestGas2MqttSettingsValidation:
    """Verify field validation constraints.

    Technique: Boundary Value Analysis — test at and beyond boundaries.
    """

    def test_i2c_bus_rejects_negative(self) -> None:
        """I2C bus number must be >= 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(i2c_bus=-1)

    def test_i2c_bus_accepts_zero(self) -> None:
        """I2C bus 0 is valid (boundary for ge=0)."""
        settings = make_gas2mqtt_settings(i2c_bus=0)
        assert settings.i2c_bus == 0

    def test_trigger_hysteresis_rejects_negative(self) -> None:
        """Hysteresis must be >= 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(trigger_hysteresis=-1)

    def test_trigger_hysteresis_accepts_zero(self) -> None:
        """Hysteresis of 0 is valid (no hysteresis band)."""
        settings = make_gas2mqtt_settings(trigger_hysteresis=0)
        assert settings.trigger_hysteresis == 0

    def test_poll_interval_rejects_zero(self) -> None:
        """Poll interval must be > 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(poll_interval=0)

    def test_poll_interval_rejects_negative(self) -> None:
        """Poll interval must be > 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(poll_interval=-1.0)

    def test_poll_interval_accepts_small_positive(self) -> None:
        """Very small poll interval (0.001s) is valid."""
        settings = make_gas2mqtt_settings(poll_interval=0.001)
        assert settings.poll_interval == 0.001

    def test_temperature_interval_rejects_zero(self) -> None:
        """Temperature interval must be > 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(temperature_interval=0)

    def test_smoothing_tau_rejects_zero(self) -> None:
        """Smoothing tau must be > 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(smoothing_tau=0)

    def test_smoothing_tau_accepts_small_positive(self) -> None:
        """Very small smoothing tau (fast response) is valid."""
        settings = make_gas2mqtt_settings(smoothing_tau=0.001)
        assert settings.smoothing_tau == 0.001

    def test_liters_per_tick_rejects_zero(self) -> None:
        """Liters per tick must be > 0."""
        with pytest.raises(ValidationError):
            make_gas2mqtt_settings(liters_per_tick=0)
