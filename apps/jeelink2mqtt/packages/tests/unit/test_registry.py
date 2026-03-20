"""Unit tests for jeelink2mqtt.registry — Sensor registry and auto-adopt.

Test Techniques Used:
- Specification-based Testing: resolve, assign, reset, drain_events contracts
- State Transition Testing: Auto-adopt lifecycle, mapping creation/replacement
- Decision Table: Auto-adopt conditions (0 stale, 1 stale, 2+ stale)
- Boundary Value Analysis: Staleness timeout edge cases
- Error Guessing: MappingConflictError, ValueError on invalid inputs
- Round-trip Testing: to_dict/from_dict serialization fidelity
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jeelink2mqtt.errors import MappingConflictError
from jeelink2mqtt.models import SensorConfig, SensorReading  # noqa: F401
from jeelink2mqtt.registry import SensorRegistry

# ======================================================================
# Helpers
# ======================================================================


def _old_timestamp(seconds_ago: float = 700.0) -> datetime:
    """Return a UTC timestamp *seconds_ago* in the past."""
    return datetime.now(UTC) - timedelta(seconds=seconds_ago)


def _fresh_timestamp() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _reading(
    sensor_id: int = 42,
    temperature: float = 21.5,
    humidity: int = 55,
    low_battery: bool = False,
    timestamp: datetime | None = None,
) -> SensorReading:
    return SensorReading(
        sensor_id=sensor_id,
        temperature=temperature,
        humidity=humidity,
        low_battery=low_battery,
        timestamp=timestamp or datetime.now(UTC),
    )


# ======================================================================
# Basic Resolution
# ======================================================================


@pytest.mark.unit
class TestResolve:
    """Specification-based tests for SensorRegistry.resolve()."""

    def test_resolve_unknown_id_returns_none(self, sensor_configs) -> None:
        """Unmapped sensor ID resolves to None.

        Technique: Specification-based — unknown ID contract.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        result = registry.resolve(999)

        # Assert
        assert result is None

    def test_resolve_known_id_returns_name(self, sensor_configs) -> None:
        """Manually assigned sensor ID resolves to its logical name.

        Technique: Specification-based — known ID contract.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 42)

        # Act
        result = registry.resolve(42)

        # Assert
        assert result == "office"


# ======================================================================
# Record Reading
# ======================================================================


@pytest.mark.unit
class TestRecordReading:
    """State Transition tests for record_reading() behaviour."""

    def test_mapped_sensor_updates_last_seen(self, sensor_configs) -> None:
        """Recording a reading for a mapped ID updates last_seen.

        Technique: State Transition — mapped ID receives fresh reading.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 42)
        new_ts = datetime.now(UTC)
        reading = _reading(sensor_id=42, timestamp=new_ts)

        # Act
        name = registry.record_reading(reading)

        # Assert
        assert name == "office"
        mapping = registry.get_mapping("office")
        assert mapping is not None
        assert mapping.last_seen == new_ts

    def test_unknown_sensor_stored_as_unmapped(self, sensor_configs) -> None:
        """Reading from an unknown ID is stashed in unmapped.

        Technique: State Transition — unknown ID stored for later adopt.
        """
        # Arrange — all sensors mapped (no stale candidates)
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 10)
        registry.assign("outdoor", 20)
        registry.assign("bedroom", 30)
        reading = _reading(sensor_id=99)

        # Act
        name = registry.record_reading(reading)

        # Assert
        assert name is None
        unmapped = registry.get_unmapped_ids()
        assert 99 in unmapped

    def test_record_reading_returns_name_for_mapped(self, sensor_configs) -> None:
        """record_reading returns the logical name for mapped IDs.

        Technique: Specification-based — return value contract.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("outdoor", 7)

        # Act
        name = registry.record_reading(_reading(sensor_id=7))

        # Assert
        assert name == "outdoor"


# ======================================================================
# Auto-Adopt (Decision Table)
# ======================================================================


@pytest.mark.unit
class TestAutoAdopt:
    """Decision Table tests for the auto-adopt algorithm (ADR-002).

    | Stale count | Action         |
    |-------------|----------------|
    | 0           | No adoption    |
    | 1           | Adopt          |
    | 2+          | No adoption    |
    """

    def test_auto_adopt_exactly_one_stale_adopts(self) -> None:
        """Exactly 1 stale sensor → auto-adopt succeeds.

        Technique: Decision Table — single stale row.
        """
        # Arrange — 2 sensors, map "office" freshly, leave "outdoor" unmapped (stale)
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        registry = SensorRegistry(configs, staleness_timeout=600.0)
        registry.assign("office", 10)

        new_reading = _reading(sensor_id=99)

        # Act
        name = registry.record_reading(new_reading)

        # Assert
        assert name == "outdoor"
        assert registry.resolve(99) == "outdoor"

    def test_auto_adopt_zero_stale_does_not_adopt(self) -> None:
        """0 stale sensors → unknown ID goes to unmapped.

        Technique: Decision Table — zero stale row.
        """
        # Arrange — all sensors freshly mapped
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        registry = SensorRegistry(configs, staleness_timeout=600.0)
        registry.assign("office", 10)
        registry.assign("outdoor", 20)

        # Act
        name = registry.record_reading(_reading(sensor_id=99))

        # Assert
        assert name is None
        assert registry.resolve(99) is None

    def test_auto_adopt_two_stale_does_not_adopt(self) -> None:
        """2+ stale sensors → ambiguous, no adoption.

        Technique: Decision Table — multiple stale row.
        """
        # Arrange — no sensors mapped, so all 3 are stale
        configs = [
            SensorConfig(name="office"),
            SensorConfig(name="outdoor"),
            SensorConfig(name="bedroom"),
        ]
        registry = SensorRegistry(configs, staleness_timeout=600.0)

        # Act
        name = registry.record_reading(_reading(sensor_id=99))

        # Assert
        assert name is None

    def test_auto_adopt_generates_event(self) -> None:
        """Auto-adopt produces a MappingEvent of type 'auto_adopt'.

        Technique: Specification-based — event generation.
        """
        # Arrange — one sensor, unmapped (stale)
        configs = [SensorConfig(name="office")]
        registry = SensorRegistry(configs)

        # Act
        registry.record_reading(_reading(sensor_id=42))
        events = registry.drain_events()

        # Assert
        assert len(events) == 1
        assert events[0].event_type == "auto_adopt"
        assert events[0].sensor_name == "office"
        assert events[0].new_sensor_id == 42
        assert events[0].old_sensor_id is None

    def test_auto_adopt_with_replacement(self) -> None:
        """Stale sensor with old mapping gets replaced on auto-adopt.

        Technique: State Transition — mapped(stale) → re-mapped(fresh).
        """
        # Arrange — one sensor mapped to old ID, mark as stale
        configs = [SensorConfig(name="office")]
        registry = SensorRegistry(configs, staleness_timeout=600.0)

        old_ts = _old_timestamp(seconds_ago=700)
        old_reading = _reading(sensor_id=10, timestamp=old_ts)
        registry.record_reading(old_reading)  # auto-adopt with ID 10
        registry.drain_events()  # clear first adopt event

        # Force staleness by checking with current time
        # The mapping's last_seen is 700s ago, timeout is 600s → stale
        new_reading = _reading(sensor_id=99)

        # Act
        name = registry.record_reading(new_reading)

        # Assert
        assert name == "office"
        assert registry.resolve(99) == "office"
        assert registry.resolve(10) is None  # old ID removed

        events = registry.drain_events()
        assert len(events) == 1
        assert events[0].old_sensor_id == 10
        assert events[0].new_sensor_id == 99


# ======================================================================
# Manual Assign
# ======================================================================


@pytest.mark.unit
class TestAssign:
    """Specification-based and Error Guessing tests for assign()."""

    def test_assign_happy_path(self, sensor_configs) -> None:
        """Manual assign creates mapping and returns event.

        Technique: Specification-based — happy path.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        event = registry.assign("office", 42)

        # Assert
        assert event.event_type == "manual_assign"
        assert event.sensor_name == "office"
        assert event.new_sensor_id == 42
        assert event.old_sensor_id is None
        assert registry.resolve(42) == "office"

    def test_assign_conflict_raises_mapping_conflict_error(
        self, sensor_configs
    ) -> None:
        """Assigning an ID already mapped to another name raises.

        Technique: Error Guessing — conflict detection.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 42)

        # Act / Assert
        with pytest.raises(MappingConflictError, match="already mapped"):
            registry.assign("outdoor", 42)

    def test_assign_same_name_same_id_is_idempotent(self, sensor_configs) -> None:
        """Re-assigning the same ID to the same name succeeds.

        Technique: Specification-based — idempotent reassignment.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 42)

        # Act — should not raise
        event = registry.assign("office", 42)

        # Assert
        assert event.event_type == "manual_assign"
        assert event.new_sensor_id == 42

    def test_assign_unknown_sensor_name_raises_value_error(self) -> None:
        """Assigning to a non-configured sensor name raises ValueError.

        Technique: Error Guessing — unknown sensor name.
        """
        # Arrange
        configs = [SensorConfig(name="office")]
        registry = SensorRegistry(configs)

        # Act / Assert
        with pytest.raises(ValueError, match="Unknown sensor name"):
            registry.assign("nonexistent", 42)

    def test_assign_replaces_old_mapping(self, sensor_configs) -> None:
        """Assigning a new ID to a name with an existing mapping replaces it.

        Technique: State Transition — old mapping replaced.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 10)

        # Act
        event = registry.assign("office", 42)

        # Assert
        assert event.old_sensor_id == 10
        assert event.new_sensor_id == 42
        assert registry.resolve(42) == "office"
        assert registry.resolve(10) is None  # old ID removed


# ======================================================================
# Reset
# ======================================================================


@pytest.mark.unit
class TestReset:
    """State Transition tests for reset() and reset_all()."""

    def test_reset_removes_mapping(self, sensor_configs) -> None:
        """reset() removes the mapping for a sensor name.

        Technique: State Transition — mapped → unmapped.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 42)

        # Act
        event = registry.reset("office")

        # Assert
        assert event is not None
        assert event.event_type == "manual_reset"
        assert event.old_sensor_id == 42
        assert event.new_sensor_id is None
        assert registry.resolve(42) is None

    def test_reset_nonexistent_returns_none(self, sensor_configs) -> None:
        """reset() on a sensor with no mapping returns None.

        Technique: Error Guessing — idempotent reset.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        result = registry.reset("office")

        # Assert
        assert result is None

    def test_reset_all_clears_all_mappings(self, sensor_configs) -> None:
        """reset_all() removes all mappings and returns events.

        Technique: State Transition — all mapped → all clear.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 10)
        registry.assign("outdoor", 20)

        # Act
        events = registry.reset_all()

        # Assert
        assert len(events) == 2
        assert all(e.event_type == "reset_all" for e in events)
        assert registry.resolve(10) is None
        assert registry.resolve(20) is None

    def test_reset_all_on_empty_returns_empty_list(self, sensor_configs) -> None:
        """reset_all() with no mappings returns an empty list.

        Technique: Boundary Value Analysis — empty state.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        events = registry.reset_all()

        # Assert
        assert events == []


# ======================================================================
# Events
# ======================================================================


@pytest.mark.unit
class TestDrainEvents:
    """Specification-based tests for drain_events()."""

    def test_drain_returns_pending_events(self, sensor_configs) -> None:
        """drain_events() returns all accumulated events.

        Technique: Specification-based — drain contract.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 10)
        registry.assign("outdoor", 20)

        # Act
        events = registry.drain_events()

        # Assert
        assert len(events) == 2

    def test_drain_clears_events(self, sensor_configs) -> None:
        """drain_events() clears the event list after returning.

        Technique: Specification-based — drain-and-clear.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)
        registry.assign("office", 10)

        # Act
        first = registry.drain_events()
        second = registry.drain_events()

        # Assert
        assert len(first) == 1
        assert len(second) == 0

    def test_drain_empty_returns_empty_list(self, sensor_configs) -> None:
        """drain_events() with no pending events returns [].

        Technique: Boundary Value Analysis — empty state.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        events = registry.drain_events()

        # Assert
        assert events == []

    def test_events_logged_for_all_operations(self, sensor_configs) -> None:
        """assign, reset, reset_all, auto-adopt all produce events.

        Technique: Specification-based — comprehensive event coverage.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act — trigger multiple event types
        registry.assign("office", 10)  # manual_assign
        registry.reset("office")  # manual_reset

        # Auto-adopt: only "office" is stale (the others are also stale = 3)
        # Let's set up for auto-adopt: map outdoor and bedroom, leave office unmapped
        registry.assign("outdoor", 20)
        registry.assign("bedroom", 30)
        # Now only "office" is stale → auto-adopt
        registry.record_reading(_reading(sensor_id=99))

        registry.reset_all()

        events = registry.drain_events()

        # Assert
        event_types = [e.event_type for e in events]
        assert "manual_assign" in event_types
        assert "manual_reset" in event_types
        assert "auto_adopt" in event_types
        assert "reset_all" in event_types


# ======================================================================
# Serialization Round-Trip
# ======================================================================


@pytest.mark.unit
class TestSerialization:
    """Round-trip Testing for to_dict/from_dict."""

    def test_round_trip_preserves_mappings(self, sensor_configs) -> None:
        """to_dict → from_dict preserves all mapping state.

        Technique: Round-trip Testing — serialization fidelity.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs, staleness_timeout=600.0)
        registry.assign("office", 42)
        registry.assign("outdoor", 7)

        # Act
        data = registry.to_dict()
        restored = SensorRegistry.from_dict(data, sensor_configs, 600.0)

        # Assert
        assert restored.resolve(42) == "office"
        assert restored.resolve(7) == "outdoor"

    def test_round_trip_preserves_unmapped(self, sensor_configs) -> None:
        """to_dict → from_dict preserves unmapped readings.

        Technique: Round-trip Testing — unmapped state fidelity.
        """
        # Arrange — all sensors mapped so unknown ID goes to unmapped
        registry = SensorRegistry(sensor_configs, staleness_timeout=600.0)
        registry.assign("office", 10)
        registry.assign("outdoor", 20)
        registry.assign("bedroom", 30)
        registry.record_reading(_reading(sensor_id=99, temperature=15.0))

        # Act
        data = registry.to_dict()
        restored = SensorRegistry.from_dict(data, sensor_configs, 600.0)

        # Assert
        unmapped = restored.get_unmapped_ids()
        assert 99 in unmapped
        assert unmapped[99].temperature == 15.0

    def test_round_trip_empty_registry(self, sensor_configs) -> None:
        """Empty registry serializes and restores cleanly.

        Technique: Boundary Value Analysis — empty state.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act
        data = registry.to_dict()
        restored = SensorRegistry.from_dict(data, sensor_configs)

        # Assert
        assert restored.resolve(42) is None
        assert restored.get_all_mappings() == {}
        assert restored.get_unmapped_ids() == {}


# ======================================================================
# Per-Sensor Staleness Timeout
# ======================================================================


@pytest.mark.unit
class TestStaleness:
    """Boundary Value Analysis tests for staleness detection."""

    def test_unmapped_sensor_is_stale(self, sensor_configs) -> None:
        """A sensor with no mapping is always stale.

        Technique: Specification-based — unmapped = stale.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs)

        # Act / Assert
        assert registry.is_stale("office") is True

    def test_freshly_mapped_sensor_is_not_stale(self, sensor_configs) -> None:
        """A sensor mapped just now is not stale.

        Technique: Specification-based — fresh mapping.
        """
        # Arrange
        registry = SensorRegistry(sensor_configs, staleness_timeout=600.0)
        registry.assign("office", 42)

        # Act / Assert
        assert registry.is_stale("office") is False

    def test_stale_after_timeout_expires(self) -> None:
        """Sensor becomes stale when last_seen exceeds global timeout.

        Technique: Boundary Value Analysis — timeout boundary.
        """
        # Arrange
        configs = [SensorConfig(name="office")]
        registry = SensorRegistry(configs, staleness_timeout=600.0)

        # Create a reading with an old timestamp (700s ago > 600s timeout)
        old_ts = _old_timestamp(seconds_ago=700)
        reading = _reading(sensor_id=42, timestamp=old_ts)
        registry.record_reading(reading)  # auto-adopts since only 1 stale

        # Act / Assert
        assert registry.is_stale("office") is True

    def test_per_sensor_timeout_overrides_global(self) -> None:
        """SensorConfig.staleness_timeout overrides the global default.

        Technique: Boundary Value Analysis — per-sensor override.
        """
        # Arrange — bedroom has 300s timeout, global is 600s
        configs = [SensorConfig(name="bedroom", staleness_timeout=300.0)]
        registry = SensorRegistry(configs, staleness_timeout=600.0)

        # Map with timestamp 400s ago — stale for 300s timeout, fresh for 600s
        old_ts = _old_timestamp(seconds_ago=400)
        reading = _reading(sensor_id=42, timestamp=old_ts)
        registry.record_reading(reading)

        # Act / Assert — bedroom uses its 300s timeout, so 400s ago = stale
        assert registry.is_stale("bedroom") is True

    def test_global_timeout_used_when_no_per_sensor(self) -> None:
        """Sensor without per-sensor timeout uses the global default.

        Technique: Boundary Value Analysis — default fallback.
        """
        # Arrange — office has no staleness_timeout (None)
        configs = [SensorConfig(name="office")]
        registry = SensorRegistry(configs, staleness_timeout=600.0)

        # Map with timestamp 500s ago — within 600s global timeout
        old_ts = _old_timestamp(seconds_ago=500)
        reading = _reading(sensor_id=42, timestamp=old_ts)
        registry.record_reading(reading)

        # Act / Assert — 500s < 600s → not stale
        assert registry.is_stale("office") is False
