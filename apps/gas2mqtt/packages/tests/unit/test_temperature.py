"""Unit tests for temperature telemetry — PT1 filter + calibration.

Tests the temperature pipeline: raw reading → calibration → PT1 filter → rounding.
The PT1 filter is provided by cosalette and configured via settings.

Test Techniques Used:
- Specification-based: Calibration formula and PT1 integration
- Boundary Value Analysis: First reading (seeds filter) vs subsequent
- Round-trip Testing: Raw → calibrated → filtered → rounded
"""

from __future__ import annotations

import pytest
from cosalette import Pt1Filter

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.settings import Gas2MqttSettings
from tests.fixtures.config import make_gas2mqtt_settings


def _calibrate(raw: int, settings: Gas2MqttSettings) -> float:
    """Apply the same calibration formula used in the temperature handler."""
    return settings.temp_scale * raw + settings.temp_offset


@pytest.mark.unit
class TestTemperaturePipeline:
    """Verify the temperature calibration + PT1 smoothing pipeline."""

    def test_first_reading_uses_raw_calibrated_value(self) -> None:
        """First PT1 update seeds the filter — returns calibrated value.

        With default calibration (scale=0.008, offset=20.3):
            raw=2500 → 0.008 * 2500 + 20.3 = 40.3

        Technique: Specification-based — first value seeds the filter.
        """
        # Arrange
        settings = make_gas2mqtt_settings()
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

        # Act
        result = pt1.update(_calibrate(2500, settings))

        # Assert
        assert round(result, 1) == 40.3

    def test_second_reading_applies_pt1_smoothing(self) -> None:
        """PT1 filter smooths the second reading.

        Technique: Specification-based — PT1 formula verification.
        First: raw=2500 → 40.3 (seeds filter)
        Second: raw=0 → 20.3
        alpha = dt/(tau+dt) = 300/(1200+300) = 0.2
        PT1: 0.8 * 40.3 + 0.2 * 20.3 = 32.24 + 4.06 = 36.3
        """
        # Arrange
        settings = make_gas2mqtt_settings()
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)
        pt1.update(_calibrate(2500, settings))  # seed

        # Act
        result = pt1.update(_calibrate(0, settings))

        # Assert
        assert round(result, 1) == 36.3

    def test_custom_calibration(self) -> None:
        """Uses configurable scale and offset.

        Technique: Equivalence Partitioning — custom calibration values.
        scale=0.01, offset=0.0, raw=1000 → 10.0
        """
        # Arrange
        settings = make_gas2mqtt_settings(temp_scale=0.01, temp_offset=0.0)
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

        # Act
        calibrated = _calibrate(1000, settings)
        result = pt1.update(calibrated)

        # Assert
        assert round(result, 1) == 10.0

    def test_rounding_to_one_decimal(self) -> None:
        """Temperature is rounded to one decimal place.

        Technique: Specification-based — output format.
        scale=0.008, offset=20.3, raw=2501 →
            0.008 * 2501 + 20.3 = 20.008 + 20.3 = 40.308 → 40.3
        """
        # Arrange
        settings = make_gas2mqtt_settings()
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

        # Act
        result = pt1.update(_calibrate(2501, settings))

        # Assert
        assert round(result, 1) == 40.3

    def test_default_tau_gives_alpha_0_2(self) -> None:
        """Default smoothing_tau=1200 with dt=300 gives alpha=0.2.

        Technique: Specification-based — PT1 alpha derivation.
        alpha = dt / (tau + dt) = 300 / (1200 + 300) = 0.2
        """
        # Arrange
        settings = make_gas2mqtt_settings()
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

        # Assert
        assert pt1.alpha == pytest.approx(0.2)

    def test_handler_produces_calibrated_state(self) -> None:
        """Full handler pipeline: magnetometer → calibrate → PT1 → round.

        Technique: Integration — exercises the same code path as main.py
        handler, but calling PT1 directly rather than through the framework.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 2500
        settings = make_gas2mqtt_settings()
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

        # Act — simulate what the handler does
        reading = mag.read()
        raw_celsius = (
            settings.temp_scale * reading.temperature_raw + settings.temp_offset
        )
        filtered = pt1.update(raw_celsius)
        result = {"temperature": round(filtered, 1)}

        # Assert
        assert result == {"temperature": 40.3}

    def test_small_tau_minimal_smoothing(self) -> None:
        """Very small tau relative to dt means nearly no smoothing.

        Technique: Boundary Value Analysis — tau near zero.
        With tau=0.001, dt=300: alpha = 300/300.001 ≈ 1.0
        """
        # Arrange
        settings = make_gas2mqtt_settings(smoothing_tau=0.001)
        pt1 = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)
        pt1.update(_calibrate(0, settings))  # seed with 20.3

        # Act — change drastically
        result = pt1.update(_calibrate(2500, settings))

        # Assert — nearly no smoothing, jumps to new value
        assert round(result, 1) == 40.3

    def test_new_filter_has_fresh_state(self) -> None:
        """Each Pt1Filter instance starts fresh — no shared state.

        Technique: Error Guessing — shared state between filters.
        """
        # Arrange
        settings = make_gas2mqtt_settings()

        pt1_a = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)
        pt1_a.update(_calibrate(2500, settings))  # seeds filter A
        pt1_a.update(_calibrate(0, settings))  # filter A is now smoothed

        # Act — new filter should start fresh
        pt1_b = Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)
        result = pt1_b.update(_calibrate(2500, settings))

        # Assert — same as first call, no carryover from filter A
        assert round(result, 1) == 40.3
