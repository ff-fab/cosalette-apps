"""Integration tests for the sensor reading pipeline.

Tests the end-to-end flow: reading → registry → filter → calibrate
using real domain objects wired together as they would be in production.

Test Techniques Used:
- State Transition Testing: Registry mapping lifecycle
- Round-trip Testing: Pipeline input → output fidelity, serialization
- Integration Testing: Component interaction verification
- Boundary Value Analysis: Staleness timeout edge case
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jeelink2mqtt.app import SharedState
from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry

# ======================================================================
# Helpers
# ======================================================================


def _pipeline(
    reading: SensorReading,
    state: SharedState,
) -> tuple[str | None, SensorReading | None]:
    """Run the registry → filter → calibrate pipeline as the receiver does.

    Returns (sensor_name, calibrated_reading) or (None, None) when the
    reading is unmapped.
    """
    name = state.registry.record_reading(reading)
    if name is None:
        return None, None

    config = state.sensor_configs.get(name)
    if config is None:
        return name, None

    filtered_temp, filtered_humidity = state.filter_bank.filter(reading)
    from dataclasses import replace

    filtered = replace(
        reading,
        temperature=filtered_temp,
        humidity=int(filtered_humidity),
    )
    calibrated = apply_calibration(filtered, config)
    return name, calibrated


# ======================================================================
# Auto-Adopt Pipeline
# ======================================================================


@pytest.mark.integration
class TestAutoAdoptPipeline:
    """Integration tests for auto-adopt → filter → calibrate flow."""

    def test_reading_auto_adopted_and_published(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """When exactly 1 sensor is stale, auto-adopt triggers and the
        full pipeline produces a calibrated reading.

        Setup: Manually assign "outdoor" so only "office" is stale.
        Then inject a reading — it should auto-adopt to "office".

        Technique: State Transition Testing — stale → adopted.
        """
        # Arrange — manually assign "outdoor" so only "office" is stale
        shared_state.registry.assign("outdoor", 99)
        shared_state.registry.drain_events()

        # Now only "office" is stale
        reading = make_reading(sensor_id=42, temperature=21.5, humidity=55)

        # Act
        name, calibrated = _pipeline(reading, shared_state)

        # Assert
        assert name == "office"
        assert calibrated is not None
        # Office offsets: temp_offset=-0.3, humidity_offset=1.0
        assert calibrated.temperature == pytest.approx(21.5 - 0.3)
        assert calibrated.humidity == 56  # 55 + round(1.0) = 56

    def test_multiple_readings_converge_through_filter(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """Send 3 readings (window=3) and verify the median filter
        produces the expected value after convergence.

        Technique: Integration Testing — filter + calibration interaction.
        """
        # Arrange — assign "outdoor" so only "office" auto-adopts
        shared_state.registry.assign("outdoor", 99)
        shared_state.registry.drain_events()

        temps = [20.0, 22.0, 21.0]
        humidities = [50, 60, 55]
        results = []

        # Act — send 3 readings through the pipeline
        for temp, hum in zip(temps, humidities, strict=True):
            reading = make_reading(sensor_id=42, temperature=temp, humidity=hum)
            name, calibrated = _pipeline(reading, shared_state)
            if calibrated is not None:
                results.append(calibrated)

        # Assert — after 3 values, median should be the middle value
        assert len(results) == 3
        last = results[-1]
        # Median of [20.0, 22.0, 21.0] = 21.0, offset -0.3 → 20.7
        assert last.temperature == pytest.approx(21.0 - 0.3)
        # Median of [50.0, 60.0, 55.0] = 55, offset +1.0 → 56
        assert last.humidity == 56

    def test_unknown_reading_goes_to_unmapped(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """When 2 sensors are stale, auto-adopt is ambiguous and the
        reading is stashed in unmapped.

        Technique: Decision Table — 2 stale → no adoption.
        """
        # Arrange — both "office" and "outdoor" stale (initial state)
        reading = make_reading(sensor_id=42)

        # Act
        name, calibrated = _pipeline(reading, shared_state)

        # Assert
        assert name is None
        assert calibrated is None
        unmapped = shared_state.registry.get_unmapped_ids()
        assert 42 in unmapped

    def test_manual_assign_followed_by_reading(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """Manually assign a sensor ID, then send a reading with that ID.
        Verify the pipeline resolves it correctly.

        Technique: State Transition — unassigned → manually assigned → reading routed.
        """
        # Arrange
        shared_state.registry.assign("outdoor", 77)
        shared_state.registry.drain_events()

        reading = make_reading(sensor_id=77, temperature=15.0, humidity=40)

        # Act
        name, calibrated = _pipeline(reading, shared_state)

        # Assert
        assert name == "outdoor"
        assert calibrated is not None
        # Outdoor has zero offset
        assert calibrated.temperature == pytest.approx(15.0)
        assert calibrated.humidity == 40


# ======================================================================
# Mapping Events
# ======================================================================


@pytest.mark.integration
class TestMappingEvents:
    """Verify that mapping lifecycle events are correctly generated."""

    def test_mapping_events_generated_on_adopt(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """Auto-adopt generates a MappingEvent with event_type, sensor_name,
        and new_sensor_id.

        Technique: State Transition Testing — event emission on state change.
        """
        # Arrange — assign "outdoor" so only "office" auto-adopts
        shared_state.registry.assign("outdoor", 99)
        shared_state.registry.drain_events()

        reading = make_reading(sensor_id=42)

        # Act
        shared_state.registry.record_reading(reading)
        events = shared_state.registry.drain_events()

        # Assert
        assert len(events) == 1
        event = events[0]
        assert event.event_type == "auto_adopt"
        assert event.sensor_name == "office"
        assert event.new_sensor_id == 42
        assert event.old_sensor_id is None


# ======================================================================
# Calibration End-to-End
# ======================================================================


@pytest.mark.integration
class TestCalibrationEndToEnd:
    """End-to-end calibration with known offsets."""

    def test_calibration_offsets_applied_correctly(
        self, shared_state: SharedState, make_reading
    ) -> None:
        """Single-value path: reading → filter (window fills with 1 value)
        → calibrate with known offsets → verify exact output.

        Technique: Round-trip Testing — input → pipeline → exact output.
        """
        # Arrange — assign "outdoor" so only "office" auto-adopts
        shared_state.registry.assign("outdoor", 99)
        shared_state.registry.drain_events()

        reading = make_reading(
            sensor_id=42,
            temperature=25.0,
            humidity=70,
        )

        # Act
        name, calibrated = _pipeline(reading, shared_state)

        # Assert
        assert name == "office"
        assert calibrated is not None
        # temp: 25.0 + (-0.3) = 24.7
        assert calibrated.temperature == pytest.approx(24.7)
        # humidity: 70 + round(1.0) = 71
        assert calibrated.humidity == 71
        # Other fields preserved
        assert calibrated.sensor_id == reading.sensor_id
        assert calibrated.low_battery == reading.low_battery


# ======================================================================
# Registry Persistence
# ======================================================================


@pytest.mark.integration
class TestRegistryPersistence:
    """Serialization round-trip with real mappings."""

    def test_registry_persistence_round_trip(
        self, sensor_configs: list[SensorConfig], make_reading
    ) -> None:
        """Create registry with auto-adopted mappings, serialize via
        to_dict, deserialize via from_dict, verify mappings preserved.

        Technique: Round-trip Testing — serialization fidelity.
        """
        # Arrange — create registry and manually assign both sensors
        registry = SensorRegistry(sensor_configs, staleness_timeout=600.0)
        registry.assign("outdoor", 99)
        registry.assign("office", 42)
        registry.drain_events()

        # Act — round-trip through serialization
        data = registry.to_dict()
        restored = SensorRegistry.from_dict(
            data, sensor_configs, staleness_timeout=600.0
        )

        # Assert — both mappings preserved
        assert restored.resolve(42) == "office"
        assert restored.resolve(99) == "outdoor"
        assert restored.get_mapping("office") is not None
        assert restored.get_mapping("office").sensor_id == 42
        assert restored.get_mapping("outdoor") is not None
        assert restored.get_mapping("outdoor").sensor_id == 99


# ======================================================================
# Staleness Detection
# ======================================================================


@pytest.mark.integration
class TestStalenessDetection:
    """Staleness timeout integration with real timestamps."""

    def test_staleness_detection_after_timeout(
        self, sensor_configs: list[SensorConfig], make_reading
    ) -> None:
        """Create a mapping with an old timestamp, verify is_stale returns True.

        Technique: Boundary Value Analysis — timestamp beyond staleness window.
        """
        # Arrange — manually assign both, then send old reading for "office"
        registry = SensorRegistry(sensor_configs, staleness_timeout=600.0)
        old_time = datetime.now(UTC) - timedelta(seconds=700)

        # Assign both sensors
        registry.assign("outdoor", 99)
        registry.assign("office", 42)
        registry.drain_events()

        # Record an old reading for "office" to make it stale
        registry.record_reading(
            make_reading(sensor_id=42, timestamp=old_time),
        )

        # Act & Assert — "office" should be stale (last_seen 700s ago)
        assert registry.is_stale("office") is True
        # "outdoor" should NOT be stale (recently assigned)
        assert registry.is_stale("outdoor") is False
