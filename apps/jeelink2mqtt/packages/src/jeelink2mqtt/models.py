"""Domain models for jeelink2mqtt.

Immutable value objects representing sensor readings, configuration,
mapping state, and mapping lifecycle events.  All models use frozen
dataclasses with ``__slots__`` for memory efficiency and immutability
guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class SensorReading:
    """Raw reading received from the JeeLink USB receiver.

    Represents a single LaCrosse frame decoded into typed fields.
    The ``sensor_id`` is ephemeral — it changes on every battery swap,
    so higher-level code must resolve it to a logical name via the
    sensor registry (see ADR-002).
    """

    sensor_id: int
    """Ephemeral LaCrosse sensor ID (changes on battery swap)."""

    temperature: float
    """Temperature in degrees Celsius."""

    humidity: int
    """Relative humidity percentage (0–100)."""

    low_battery: bool
    """Battery warning flag from the sensor frame."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    """When the reading was received (defaults to *now* in UTC)."""


@dataclass(frozen=True, slots=True)
class SensorConfig:
    """Per-sensor configuration loaded from application settings.

    Each configured sensor gets a logical *name* (e.g. ``"office"``,
    ``"outdoor"``) that remains stable across battery swaps and ID
    changes.  Calibration offsets allow compensating for individual
    sensor inaccuracies.
    """

    name: str
    """Logical sensor name (e.g. ``"office"``, ``"outdoor"``)."""

    temp_offset: float = 0.0
    """Calibration offset added to temperature readings (°C)."""

    humidity_offset: float = 0.0
    """Calibration offset added to humidity readings (percentage points)."""

    staleness_timeout: float | None = None
    """Per-sensor staleness override in seconds (``None`` = use global)."""


@dataclass(frozen=True, slots=True)
class SensorMapping:
    """Runtime mapping state for one sensor.

    Tracks which ephemeral LaCrosse ID is currently associated with a
    logical sensor name.  Updated when a battery swap causes a new ID
    to appear (auto-adopt) or via manual assignment.
    """

    sensor_id: int
    """Currently mapped LaCrosse ID."""

    sensor_name: str
    """Logical sensor name this ID is mapped to."""

    mapped_at: datetime
    """When this mapping was created (e.g. battery swap timestamp)."""

    last_seen: datetime
    """Last time a reading was received for this mapping."""


@dataclass(frozen=True, slots=True)
class MappingEvent:
    """Immutable event recording a mapping change.

    Produced by the sensor registry whenever a mapping is created,
    changed, or reset.  Can be published to MQTT for observability
    or persisted for audit trails.
    """

    event_type: str
    """One of ``"auto_adopt"``, ``"manual_assign"``, ``"manual_reset"``,
    ``"reset_all"``."""

    sensor_name: str
    """Affected logical sensor name."""

    old_sensor_id: int | None
    """Previous LaCrosse ID (``None`` if first assignment)."""

    new_sensor_id: int | None
    """New LaCrosse ID (``None`` if reset)."""

    timestamp: datetime
    """When the event occurred."""

    reason: str
    """Human-readable explanation of the mapping change."""
