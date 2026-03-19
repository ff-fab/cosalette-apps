"""Sensor registry — manages ephemeral ID to logical name mappings.

Implements the auto-adopt algorithm (ADR-002) and satisfies the
SensorRegistryPort protocol for read access.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from jeelink2mqtt.errors import MappingConflictError
from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorMapping, SensorReading


class SensorRegistry:
    """Manages ephemeral LaCrosse ID → logical sensor name mappings.

    The registry maintains a bidirectional index: *name → mapping* for
    configuration lookups and *id → name* for fast O(1) frame routing.
    Unmapped IDs are held in a separate dict until they can be
    auto-adopted or manually assigned.

    .. note:: Not thread-safe.  Designed to run within a single asyncio
       task inside the cosalette event loop.
    """

    def __init__(
        self,
        sensors: list[SensorConfig],
        staleness_timeout: float = 600.0,
    ) -> None:
        self._staleness_timeout = staleness_timeout

        self._sensor_configs: dict[str, SensorConfig] = {s.name: s for s in sensors}
        self._mappings: dict[str, SensorMapping] = {}
        self._id_index: dict[int, str] = {}
        self._unmapped: dict[int, SensorReading] = {}
        self._events: list[MappingEvent] = []

    # -- SensorRegistryPort (read-only) ------------------------------------

    def resolve(self, sensor_id: int) -> str | None:
        """Resolve an ephemeral sensor ID to a logical name."""
        return self._id_index.get(sensor_id)

    def is_stale(self, sensor_name: str) -> bool:
        """Check whether a sensor has exceeded its staleness timeout.

        Uses the per-sensor override if configured, otherwise the global
        timeout.  Returns ``True`` when no mapping exists at all.
        """
        mapping = self._mappings.get(sensor_name)
        if mapping is None:
            return True

        timeout = self._effective_timeout(sensor_name)
        elapsed = (datetime.now(UTC) - mapping.last_seen).total_seconds()
        return elapsed > timeout

    def get_mapping(self, sensor_name: str) -> SensorMapping | None:
        """Get the current mapping for a logical sensor name."""
        return self._mappings.get(sensor_name)

    def get_all_mappings(self) -> dict[str, SensorMapping]:
        """Return a shallow copy of all active mappings."""
        return dict(self._mappings)

    def get_unmapped_ids(self) -> dict[int, SensorReading]:
        """Return a shallow copy of recently-seen unmapped IDs."""
        return dict(self._unmapped)

    # -- Write methods -----------------------------------------------------

    def record_reading(self, reading: SensorReading) -> str | None:
        """Process an incoming sensor frame.

        1. If the ID is already mapped, update ``last_seen`` and return
           the logical name.
        2. Otherwise attempt auto-adopt.  If adopted, return the name;
           if not, stash the reading in ``_unmapped`` and return ``None``.
        """
        name = self._id_index.get(reading.sensor_id)

        if name is not None:
            # Known ID — update last_seen (frozen dataclass → replace).
            old = self._mappings[name]
            self._mappings[name] = replace(old, last_seen=reading.timestamp)
            self._unmapped.pop(reading.sensor_id, None)
            return name

        # Unknown ID — try auto-adopt.
        adopted_name = self._try_auto_adopt(reading)
        if adopted_name is not None:
            self._unmapped.pop(reading.sensor_id, None)
            return adopted_name

        self._unmapped[reading.sensor_id] = reading
        return None

    def _try_auto_adopt(self, reading: SensorReading) -> str | None:
        """Implement ADR-002 auto-adopt algorithm.

        Auto-adopt succeeds only when *exactly one* configured sensor is
        currently stale (no mapping or last_seen beyond the timeout).
        This avoids ambiguous assignments when multiple sensors are due
        for a battery swap.
        """
        stale_names: list[str] = [
            name for name in self._sensor_configs if self.is_stale(name)
        ]

        if len(stale_names) != 1:
            return None

        name = stale_names[0]
        old_mapping = self._mappings.get(name)
        old_id = old_mapping.sensor_id if old_mapping is not None else None

        # Remove stale reverse index entry.
        if old_id is not None:
            self._id_index.pop(old_id, None)

        now = reading.timestamp
        self._mappings[name] = SensorMapping(
            sensor_id=reading.sensor_id,
            sensor_name=name,
            mapped_at=now,
            last_seen=now,
        )
        self._id_index[reading.sensor_id] = name

        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name=name,
            old_sensor_id=old_id,
            new_sensor_id=reading.sensor_id,
            timestamp=now,
            reason=f"Auto-adopted sensor ID {reading.sensor_id} for '{name}'"
            + (f" (replaced ID {old_id})" if old_id is not None else ""),
        )
        self._events.append(event)
        return name

    def assign(self, sensor_name: str, sensor_id: int) -> MappingEvent:
        """Manually assign an ephemeral ID to a logical sensor name.

        Raises:
            MappingConflictError: If ``sensor_id`` is already mapped to
                a *different* sensor name.
            ValueError: If ``sensor_name`` is not a configured sensor.
        """
        if sensor_name not in self._sensor_configs:
            msg = (
                f"Unknown sensor name '{sensor_name}' — "
                "must be one of the configured sensors"
            )
            raise ValueError(msg)

        existing_name = self._id_index.get(sensor_id)
        if existing_name is not None and existing_name != sensor_name:
            msg = (
                f"Sensor ID {sensor_id} is already mapped to "
                f"'{existing_name}', cannot assign to '{sensor_name}'"
            )
            raise MappingConflictError(msg)

        old_mapping = self._mappings.get(sensor_name)
        old_id = old_mapping.sensor_id if old_mapping is not None else None

        # Remove old reverse index entry if reassigning.
        if old_id is not None:
            self._id_index.pop(old_id, None)

        now = datetime.now(UTC)
        self._mappings[sensor_name] = SensorMapping(
            sensor_id=sensor_id,
            sensor_name=sensor_name,
            mapped_at=now,
            last_seen=now,
        )
        self._id_index[sensor_id] = sensor_name
        self._unmapped.pop(sensor_id, None)

        event = MappingEvent(
            event_type="manual_assign",
            sensor_name=sensor_name,
            old_sensor_id=old_id,
            new_sensor_id=sensor_id,
            timestamp=now,
            reason=f"Manually assigned sensor ID {sensor_id} to '{sensor_name}'",
        )
        self._events.append(event)
        return event

    def reset(self, sensor_name: str) -> MappingEvent | None:
        """Remove the mapping for a sensor name.

        Returns the event, or ``None`` if no mapping existed.
        """
        mapping = self._mappings.pop(sensor_name, None)
        if mapping is None:
            return None

        self._id_index.pop(mapping.sensor_id, None)

        event = MappingEvent(
            event_type="manual_reset",
            sensor_name=sensor_name,
            old_sensor_id=mapping.sensor_id,
            new_sensor_id=None,
            timestamp=datetime.now(UTC),
            reason=f"Mapping reset for '{sensor_name}'",
        )
        self._events.append(event)
        return event

    def reset_all(self) -> list[MappingEvent]:
        """Remove all mappings.  Returns one event per cleared mapping."""
        events: list[MappingEvent] = []
        now = datetime.now(UTC)

        for name, mapping in list(self._mappings.items()):
            event = MappingEvent(
                event_type="reset_all",
                sensor_name=name,
                old_sensor_id=mapping.sensor_id,
                new_sensor_id=None,
                timestamp=now,
                reason="All mappings reset",
            )
            events.append(event)

        self._mappings.clear()
        self._id_index.clear()
        self._events.extend(events)
        return events

    def drain_events(self) -> list[MappingEvent]:
        """Return and clear all pending mapping events."""
        events = list(self._events)
        self._events.clear()
        return events

    # -- Serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        """Serialize registry state for JSON persistence."""
        return {
            "mappings": {
                name: {
                    "sensor_id": m.sensor_id,
                    "sensor_name": m.sensor_name,
                    "mapped_at": m.mapped_at.isoformat(),
                    "last_seen": m.last_seen.isoformat(),
                }
                for name, m in self._mappings.items()
            },
            "unmapped": {
                str(sid): {
                    "sensor_id": r.sensor_id,
                    "temperature": r.temperature,
                    "humidity": r.humidity,
                    "low_battery": r.low_battery,
                    "timestamp": r.timestamp.isoformat(),
                }
                for sid, r in self._unmapped.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        sensors: list[SensorConfig],
        staleness_timeout: float = 600.0,
    ) -> SensorRegistry:
        """Restore registry state from persisted data."""
        registry = cls(sensors=sensors, staleness_timeout=staleness_timeout)

        for _name, mdata in data.get("mappings", {}).items():
            mapping = SensorMapping(
                sensor_id=mdata["sensor_id"],
                sensor_name=mdata["sensor_name"],
                mapped_at=datetime.fromisoformat(mdata["mapped_at"]),
                last_seen=datetime.fromisoformat(mdata["last_seen"]),
            )
            registry._mappings[mapping.sensor_name] = mapping
            registry._id_index[mapping.sensor_id] = mapping.sensor_name

        for _sid_str, rdata in data.get("unmapped", {}).items():
            reading = SensorReading(
                sensor_id=rdata["sensor_id"],
                temperature=rdata["temperature"],
                humidity=rdata["humidity"],
                low_battery=rdata["low_battery"],
                timestamp=datetime.fromisoformat(rdata["timestamp"]),
            )
            registry._unmapped[reading.sensor_id] = reading

        return registry

    # -- Helpers -----------------------------------------------------------

    def _effective_timeout(self, sensor_name: str) -> float:
        """Return the staleness timeout for *sensor_name*.

        Uses the per-sensor override when configured, falling back to
        the global default.
        """
        cfg = self._sensor_configs.get(sensor_name)
        if cfg is not None and cfg.staleness_timeout is not None:
            return cfg.staleness_timeout
        return self._staleness_timeout
