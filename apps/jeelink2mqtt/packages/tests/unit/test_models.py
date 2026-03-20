"""Unit tests for jeelink2mqtt.models — Immutable domain value objects.

Test Techniques Used:
- Specification-based Testing: Verifying constructor contracts and defaults
- Error Guessing: Frozen dataclass mutation raises FrozenInstanceError
- Equivalence Partitioning: Valid construction, default values, equality
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from jeelink2mqtt.models import (
    MappingEvent,
    SensorConfig,
    SensorMapping,
    SensorReading,
)

# ======================================================================
# SensorReading
# ======================================================================


@pytest.mark.unit
class TestSensorReading:
    """Specification-based tests for the SensorReading frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """SensorReading stores all provided values.

        Technique: Specification-based — verify constructor contract.
        """
        # Arrange
        ts = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)

        # Act
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=ts,
        )

        # Assert
        assert reading.sensor_id == 42
        assert reading.temperature == 21.5
        assert reading.humidity == 55
        assert reading.low_battery is False
        assert reading.timestamp == ts

    def test_timestamp_defaults_to_utc_now(self) -> None:
        """Omitting timestamp uses current UTC time.

        Technique: Specification-based — default value behaviour.
        """
        # Arrange
        before = datetime.now(UTC)

        # Act
        reading = SensorReading(
            sensor_id=1, temperature=20.0, humidity=50, low_battery=False
        )

        # Assert
        after = datetime.now(UTC)
        assert before <= reading.timestamp <= after

    def test_frozen_immutability(self) -> None:
        """Mutation of a frozen dataclass raises FrozenInstanceError.

        Technique: Error Guessing — anticipating specific failure mode.
        """
        # Arrange
        reading = SensorReading(
            sensor_id=1, temperature=20.0, humidity=50, low_battery=False
        )

        # Act / Assert
        with pytest.raises(dataclasses.FrozenInstanceError):
            reading.temperature = 99.0  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """slots=True means instances have no __dict__.

        Technique: Specification-based — structural guarantee.
        """
        # Arrange
        reading = SensorReading(
            sensor_id=1, temperature=20.0, humidity=50, low_battery=False
        )

        # Assert
        assert not hasattr(reading, "__dict__")

    def test_equality_identical_values(self) -> None:
        """Two SensorReadings with identical values are equal.

        Technique: Equivalence Partitioning — equal inputs.
        """
        # Arrange
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        kwargs = {
            "sensor_id": 10,
            "temperature": 22.0,
            "humidity": 60,
            "low_battery": True,
            "timestamp": ts,
        }

        # Act
        a = SensorReading(**kwargs)
        b = SensorReading(**kwargs)

        # Assert
        assert a == b

    def test_equality_different_values(self) -> None:
        """Two SensorReadings with different values are NOT equal.

        Technique: Equivalence Partitioning — unequal inputs.
        """
        # Arrange
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        a = SensorReading(
            sensor_id=10, temperature=22.0, humidity=60, low_battery=True, timestamp=ts
        )
        b = SensorReading(
            sensor_id=11, temperature=22.0, humidity=60, low_battery=True, timestamp=ts
        )

        # Assert
        assert a != b


# ======================================================================
# SensorConfig
# ======================================================================


@pytest.mark.unit
class TestSensorConfig:
    """Specification-based tests for the SensorConfig frozen dataclass."""

    def test_construction_with_defaults(self) -> None:
        """SensorConfig applies correct defaults for optional fields.

        Technique: Specification-based — default values.
        """
        # Act
        cfg = SensorConfig(name="office")

        # Assert
        assert cfg.name == "office"
        assert cfg.temp_offset == 0.0
        assert cfg.humidity_offset == 0.0
        assert cfg.staleness_timeout is None

    def test_construction_with_all_fields(self) -> None:
        """SensorConfig stores all provided values.

        Technique: Specification-based — constructor contract.
        """
        # Act
        cfg = SensorConfig(
            name="outdoor",
            temp_offset=-0.5,
            humidity_offset=2.0,
            staleness_timeout=300.0,
        )

        # Assert
        assert cfg.name == "outdoor"
        assert cfg.temp_offset == -0.5
        assert cfg.humidity_offset == 2.0
        assert cfg.staleness_timeout == 300.0

    def test_frozen_immutability(self) -> None:
        """Mutation of a frozen SensorConfig raises FrozenInstanceError.

        Technique: Error Guessing — immutability enforcement.
        """
        # Arrange
        cfg = SensorConfig(name="office")

        # Act / Assert
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.name = "changed"  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """slots=True means no __dict__ attribute.

        Technique: Specification-based — structural guarantee.
        """
        # Arrange
        cfg = SensorConfig(name="office")

        # Assert
        assert not hasattr(cfg, "__dict__")

    def test_equality_identical_values(self) -> None:
        """Two SensorConfigs with same values are equal.

        Technique: Equivalence Partitioning — equal inputs.
        """
        # Arrange / Act
        a = SensorConfig(name="office", temp_offset=1.0)
        b = SensorConfig(name="office", temp_offset=1.0)

        # Assert
        assert a == b


# ======================================================================
# SensorMapping
# ======================================================================


@pytest.mark.unit
class TestSensorMapping:
    """Specification-based tests for the SensorMapping frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """SensorMapping stores all provided values.

        Technique: Specification-based — constructor contract.
        """
        # Arrange
        ts = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)

        # Act
        mapping = SensorMapping(
            sensor_id=42,
            sensor_name="office",
            mapped_at=ts,
            last_seen=ts,
        )

        # Assert
        assert mapping.sensor_id == 42
        assert mapping.sensor_name == "office"
        assert mapping.mapped_at == ts
        assert mapping.last_seen == ts

    def test_frozen_immutability(self) -> None:
        """Mutation of a frozen SensorMapping raises FrozenInstanceError.

        Technique: Error Guessing — immutability enforcement.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        mapping = SensorMapping(
            sensor_id=42, sensor_name="office", mapped_at=ts, last_seen=ts
        )

        # Act / Assert
        with pytest.raises(dataclasses.FrozenInstanceError):
            mapping.sensor_id = 99  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """slots=True means no __dict__ attribute.

        Technique: Specification-based — structural guarantee.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        mapping = SensorMapping(
            sensor_id=42, sensor_name="office", mapped_at=ts, last_seen=ts
        )

        # Assert
        assert not hasattr(mapping, "__dict__")

    def test_equality_identical_values(self) -> None:
        """Two SensorMappings with same values are equal.

        Technique: Equivalence Partitioning — equal inputs.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        kwargs = {
            "sensor_id": 42,
            "sensor_name": "office",
            "mapped_at": ts,
            "last_seen": ts,
        }

        # Act
        a = SensorMapping(**kwargs)
        b = SensorMapping(**kwargs)

        # Assert
        assert a == b


# ======================================================================
# MappingEvent
# ======================================================================


@pytest.mark.unit
class TestMappingEvent:
    """Specification-based tests for the MappingEvent frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """MappingEvent stores all provided values.

        Technique: Specification-based — constructor contract.
        """
        # Arrange
        ts = datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC)

        # Act
        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name="office",
            old_sensor_id=None,
            new_sensor_id=42,
            timestamp=ts,
            reason="Auto-adopted sensor ID 42 for 'office'",
        )

        # Assert
        assert event.event_type == "auto_adopt"
        assert event.sensor_name == "office"
        assert event.old_sensor_id is None
        assert event.new_sensor_id == 42
        assert event.timestamp == ts
        assert "Auto-adopted" in event.reason

    def test_construction_with_old_and_new_ids(self) -> None:
        """MappingEvent can represent a replacement (both IDs present).

        Technique: Specification-based — replacement scenario.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)

        # Act
        event = MappingEvent(
            event_type="manual_assign",
            sensor_name="office",
            old_sensor_id=10,
            new_sensor_id=42,
            timestamp=ts,
            reason="Manually assigned",
        )

        # Assert
        assert event.old_sensor_id == 10
        assert event.new_sensor_id == 42

    def test_frozen_immutability(self) -> None:
        """Mutation of a frozen MappingEvent raises FrozenInstanceError.

        Technique: Error Guessing — immutability enforcement.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name="office",
            old_sensor_id=None,
            new_sensor_id=42,
            timestamp=ts,
            reason="test",
        )

        # Act / Assert
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.event_type = "manual_assign"  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """slots=True means no __dict__ attribute.

        Technique: Specification-based — structural guarantee.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name="office",
            old_sensor_id=None,
            new_sensor_id=42,
            timestamp=ts,
            reason="test",
        )

        # Assert
        assert not hasattr(event, "__dict__")

    def test_equality_identical_values(self) -> None:
        """Two MappingEvents with same values are equal.

        Technique: Equivalence Partitioning — equal inputs.
        """
        # Arrange
        ts = datetime(2026, 3, 4, tzinfo=UTC)
        kwargs = {
            "event_type": "auto_adopt",
            "sensor_name": "office",
            "old_sensor_id": None,
            "new_sensor_id": 42,
            "timestamp": ts,
            "reason": "test",
        }

        # Act
        a = MappingEvent(**kwargs)
        b = MappingEvent(**kwargs)

        # Assert
        assert a == b
