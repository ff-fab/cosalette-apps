"""Unit tests for jeelink2mqtt.calibration — Sensor offset application.

Test Techniques Used:
- Equivalence Partitioning: Zero, positive, negative offsets via @parametrize
- Boundary Value Analysis: Humidity clamping at 0 and 100
- Specification-based Testing: dataclasses.replace preserves original
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.models import SensorConfig, SensorReading


@pytest.mark.unit
class TestApplyCalibration:
    """Specification-based and BVA tests for apply_calibration."""

    def test_zero_offsets_returns_same_values(self, make_reading) -> None:
        """Zero offsets produce identical temperature and humidity.

        Technique: Equivalence Partitioning — identity class.
        """
        # Arrange
        reading = make_reading(temperature=21.5, humidity=55)
        config = SensorConfig(name="office")  # defaults: 0.0, 0.0

        # Act
        result = apply_calibration(reading, config)

        # Assert
        assert result.temperature == 21.5
        assert result.humidity == 55

    @pytest.mark.parametrize(
        ("temp", "offset", "expected"),
        [
            (20.0, 1.5, 21.5),
            (20.0, -2.0, 18.0),
            (0.0, 0.1, 0.1),
            (-5.0, -0.5, -5.5),
        ],
        ids=["positive", "negative", "near-zero", "below-zero"],
    )
    def test_temperature_offset_applied(
        self, make_reading, temp: float, offset: float, expected: float
    ) -> None:
        """Temperature offset is added directly.

        Technique: Equivalence Partitioning — positive/negative offsets.
        """
        # Arrange
        reading = make_reading(temperature=temp)
        config = SensorConfig(name="test", temp_offset=offset)

        # Act
        result = apply_calibration(reading, config)

        # Assert
        assert result.temperature == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("humidity", "offset", "expected"),
        [
            (50, 5.0, 55),
            (50, -10.0, 40),
            (50, 0.4, 50),  # floor(0.4 + 0.5) = 0 → 50
            (50, 0.5, 51),  # floor(0.5 + 0.5) = 1 → 51 (half-up)
            (50, 0.6, 51),  # floor(0.6 + 0.5) = 1 → 51
        ],
        ids=["positive", "negative", "round-down", "half-up", "round-up"],
    )
    def test_humidity_offset_with_half_up_rounding(
        self, make_reading, humidity: int, offset: float, expected: int
    ) -> None:
        """Humidity uses math.floor(offset + 0.5) rounding (half-up).

        Technique: Boundary Value Analysis — rounding boundaries.
        """
        # Arrange
        reading = make_reading(humidity=humidity)
        config = SensorConfig(name="test", humidity_offset=offset)

        # Act
        result = apply_calibration(reading, config)

        # Assert
        assert result.humidity == expected

    def test_humidity_clamped_at_100(self, make_reading) -> None:
        """Humidity never exceeds 100 after calibration.

        Technique: Boundary Value Analysis — upper bound.
        """
        # Arrange
        reading = make_reading(humidity=98)
        config = SensorConfig(name="test", humidity_offset=5.0)

        # Act
        result = apply_calibration(reading, config)

        # Assert
        assert result.humidity == 100

    def test_humidity_clamped_at_0(self, make_reading) -> None:
        """Humidity never goes below 0 after calibration.

        Technique: Boundary Value Analysis — lower bound.
        """
        # Arrange
        reading = make_reading(humidity=2)
        config = SensorConfig(name="test", humidity_offset=-10.0)

        # Act
        result = apply_calibration(reading, config)

        # Assert
        assert result.humidity == 0

    def test_original_reading_unchanged(self, make_reading) -> None:
        """apply_calibration uses replace() — original is immutable.

        Technique: Specification-based — side-effect freedom.
        """
        # Arrange
        reading = make_reading(temperature=20.0, humidity=50)
        config = SensorConfig(name="test", temp_offset=5.0, humidity_offset=10.0)

        # Act
        result = apply_calibration(reading, config)

        # Assert — original unchanged
        assert reading.temperature == 20.0
        assert reading.humidity == 50
        # result has new values
        assert result.temperature == 25.0
        assert result.humidity == 60

    def test_preserves_all_fields(self) -> None:
        """replace() preserves sensor_id, low_battery, timestamp.

        Technique: Specification-based — field preservation contract.
        """
        # Arrange
        ts = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)
        reading = SensorReading(
            sensor_id=99,
            temperature=20.0,
            humidity=50,
            low_battery=True,
            timestamp=ts,
        )
        config = SensorConfig(name="test", temp_offset=1.0, humidity_offset=2.0)

        # Act
        result = apply_calibration(reading, config)

        # Assert — non-calibrated fields preserved
        assert result.sensor_id == 99
        assert result.low_battery is True
        assert result.timestamp == ts
        # calibrated fields changed
        assert result.temperature == 21.0
        assert result.humidity == 52
