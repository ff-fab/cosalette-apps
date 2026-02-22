"""Unit tests for gas2mqtt/devices/temperature.py — Temperature device.

Test Techniques Used:
- Specification-based: Calibration formula and EWMA integration
- Boundary Value Analysis: First reading (no smoothing) vs subsequent
- Round-trip Testing: Raw → calibrated → filtered → rounded
- Error Guessing: Shared state between handlers
"""

from __future__ import annotations

import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.temperature import make_temperature_handler
from tests.fixtures.config import make_gas2mqtt_settings


@pytest.mark.unit
class TestTemperatureHandler:
    """Verify temperature handler applies calibration and EWMA filter."""

    async def test_first_reading_uses_raw_calibrated_value(self) -> None:
        """First reading applies calibration but no EWMA smoothing.

        Technique: Specification-based — first value seeds the filter.
        With default calibration (scale=0.008, offset=20.3):
            raw=2500 → 0.008 * 2500 + 20.3 = 40.3
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2500
        settings = make_gas2mqtt_settings()
        handler = make_temperature_handler(mag, settings)

        # Act
        result = await handler()

        # Assert
        assert result == {"temperature": 40.3}

    async def test_second_reading_applies_ewma_smoothing(self) -> None:
        """EWMA filter smooths the second reading.

        Technique: Specification-based — EWMA formula verification.
        First: raw=2500 → 40.3 (seeds filter)
        Second: raw=0 → 0.008*0 + 20.3 = 20.3
        EWMA: (1-0.2)*40.3 + 0.2*20.3 = 32.24 + 4.06 = 36.3
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2500
        settings = make_gas2mqtt_settings()  # alpha=0.2
        handler = make_temperature_handler(mag, settings)
        await handler()  # seed the filter

        # Act
        mag.temperature_raw = 0
        result = await handler()

        # Assert
        assert result == {"temperature": 36.3}

    async def test_custom_calibration(self) -> None:
        """Uses configurable scale and offset.

        Technique: Equivalence Partitioning — custom calibration values.
        scale=0.01, offset=0.0, raw=1000 → 0.01 * 1000 + 0 = 10.0
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 1000
        settings = make_gas2mqtt_settings(temp_scale=0.01, temp_offset=0.0)
        handler = make_temperature_handler(mag, settings)

        # Act
        result = await handler()

        # Assert
        assert result == {"temperature": 10.0}

    async def test_rounding_to_one_decimal(self) -> None:
        """Temperature is rounded to one decimal place.

        Technique: Specification-based — output format.
        scale=0.008, offset=20.3, raw=2501 →
            0.008 * 2501 + 20.3 = 20.008 + 20.3 = 40.308 → 40.3
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2501
        settings = make_gas2mqtt_settings()
        handler = make_temperature_handler(mag, settings)

        # Act
        result = await handler()

        # Assert
        assert result["temperature"] == 40.3

    async def test_alpha_one_no_smoothing(self) -> None:
        """Alpha=1.0 means each reading replaces the previous entirely.

        Technique: Boundary Value Analysis — alpha at maximum.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 0  # → 0.008*0 + 20.3 = 20.3
        settings = make_gas2mqtt_settings(ewma_alpha=1.0)
        handler = make_temperature_handler(mag, settings)
        await handler()  # seed

        # Act — change drastically
        mag.temperature_raw = 2500  # → 40.3
        result = await handler()

        # Assert — no smoothing, jumps to new value
        assert result == {"temperature": 40.3}

    async def test_new_handler_has_fresh_filter(self) -> None:
        """Each call to make_temperature_handler creates a new EWMA filter.

        Technique: Error Guessing — shared state between handlers.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2500
        settings = make_gas2mqtt_settings()

        handler1 = make_temperature_handler(mag, settings)
        await handler1()  # seeds handler1's filter

        # Act — new handler should start fresh
        handler2 = make_temperature_handler(mag, settings)
        result = await handler2()

        # Assert — same as first call, no carryover
        assert result == {"temperature": 40.3}
