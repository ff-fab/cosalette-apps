"""Unit tests for jeelink2mqtt.pipeline — filter_and_calibrate helper.

Test Techniques Used:
- Specification-based Testing: verifies the filter → calibrate composition
- Equivalence Partitioning: zero offsets, non-zero offsets, multi-reading median convergence
- State Transition Testing: median filter window convergence
- Boundary Value Analysis: rounding and metadata preservation
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.pipeline import filter_and_calibrate
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.state import SharedState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    sensor_configs: list[SensorConfig] | None = None,
    window: int = 3,
) -> SharedState:
    configs = sensor_configs or [SensorConfig(name="office")]
    return SharedState(
        registry=SensorRegistry(sensors=configs, staleness_timeout=600.0),
        filter_bank=FilterBank(window=window),
        sensor_configs={c.name: c for c in configs},
    )


def _reading(
    *,
    sensor_id: int = 42,
    temperature: float = 20.0,
    humidity: int = 50,
    low_battery: bool = False,
    timestamp: datetime | None = None,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        temperature=temperature,
        humidity=humidity,
        low_battery=low_battery,
        timestamp=timestamp or datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
    )


# ===========================================================================
# filter_and_calibrate
# ===========================================================================


@pytest.mark.unit
class TestFilterAndCalibrate:
    """Verifies the filter → calibrate composition exposed by pipeline.py."""

    def test_applies_calibration_offset(self) -> None:
        """Non-zero offsets are applied after filtering.

        Technique: Specification-based — calibration adds offset to filtered value.
        """
        config = SensorConfig(name="office", temp_offset=1.0, humidity_offset=2.0)
        state = _make_state(sensor_configs=[config], window=3)
        reading = _reading(sensor_id=42, temperature=20.0, humidity=50)

        result = filter_and_calibrate(reading, config, state)

        # First reading through median window passes through unchanged, then offset applied
        assert result.temperature == pytest.approx(21.0)  # 20.0 + 1.0
        assert result.humidity == 52  # 50 + floor(2.0 + 0.5)

    def test_zero_offsets_preserves_filtered_values(self) -> None:
        """Zero calibration offsets: output equals filtered input.

        Technique: Equivalence Partitioning — identity calibration.
        """
        config = SensorConfig(name="office")
        state = _make_state(sensor_configs=[config], window=3)
        reading = _reading(temperature=22.0, humidity=60)

        result = filter_and_calibrate(reading, config, state)

        assert result.temperature == pytest.approx(22.0)
        assert result.humidity == 60

    def test_preserves_metadata_fields(self) -> None:
        """sensor_id, low_battery, and timestamp are preserved through the pipeline.

        Technique: Specification-based — dataclasses.replace contract.
        """
        ts = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        config = SensorConfig(name="office", temp_offset=0.5)
        state = _make_state(sensor_configs=[config], window=3)
        reading = _reading(sensor_id=99, low_battery=True, timestamp=ts)

        result = filter_and_calibrate(reading, config, state)

        assert result.sensor_id == 99
        assert result.low_battery is True
        assert result.timestamp == ts

    def test_median_filter_converges_over_window(self) -> None:
        """After filling the median window, outliers are suppressed.

        Technique: State Transition Testing — filter state accumulates across calls.
        Three readings: 20.0, 100.0, 20.0 → median of the window is 20.0.
        """
        config = SensorConfig(name="office")
        state = _make_state(sensor_configs=[config], window=3)

        filter_and_calibrate(_reading(sensor_id=42, temperature=20.0), config, state)
        filter_and_calibrate(_reading(sensor_id=42, temperature=100.0), config, state)
        result = filter_and_calibrate(
            _reading(sensor_id=42, temperature=20.0), config, state
        )

        # Median of [20.0, 100.0, 20.0] = 20.0 — outlier suppressed
        assert result.temperature == pytest.approx(20.0)

    def test_separate_sensor_ids_maintain_independent_filters(self) -> None:
        """Different sensor IDs use separate filter state.

        Technique: Equivalence Partitioning — per-sensor filter isolation.
        """
        config_a = SensorConfig(name="office")
        config_b = SensorConfig(name="outdoor")
        state = _make_state(sensor_configs=[config_a, config_b], window=3)

        # Feed sensor 1 with a high value
        filter_and_calibrate(_reading(sensor_id=1, temperature=50.0), config_a, state)

        # Sensor 2's first reading should not be influenced by sensor 1's history
        result_b = filter_and_calibrate(
            _reading(sensor_id=2, temperature=20.0), config_b, state
        )

        assert result_b.temperature == pytest.approx(20.0)
