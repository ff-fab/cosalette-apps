"""Fake magnetometer adapter for testing and dry-run mode.

Provides deterministic readings for unit tests and --dry-run operation.
The bz value can be controlled to simulate trigger events.
"""

from __future__ import annotations

import copy

from gas2mqtt.ports import MagneticReading


class FakeMagnetometer:
    """Test double for MagnetometerPort.

    Returns configurable, deterministic readings. Useful for:
    - Unit tests (set specific bz values to test Schmitt trigger)
    - Dry-run mode (returns safe default values)

    Attributes:
        bx: Configurable X-axis value (default 0).
        by: Configurable Y-axis value (default 0).
        bz: Configurable Z-axis value (default 0).
        temperature_raw: Configurable raw temperature value (default 0).
        initialized: Whether initialize() has been called.
        closed: Whether close() has been called.
    """

    def __init__(self) -> None:
        self.bx: int = 0
        self.by: int = 0
        self.bz: int = 0
        self.temperature_raw: int = 0
        self.initialized: bool = False
        self.closed: bool = False

    def initialize(self) -> None:
        """Mark the fake sensor as initialized."""
        self.initialized = True

    def read(self) -> MagneticReading:
        """Return a MagneticReading with the current configured values."""
        return MagneticReading(
            bx=self.bx,
            by=self.by,
            bz=self.bz,
            temperature_raw=self.temperature_raw,
        )

    def close(self) -> None:
        """Mark the fake sensor as closed."""
        self.closed = True


class NullStorage:
    """No-op adapter for StateStoragePort.

    Used when persistence is disabled (state_file is None)
    or in dry-run mode. load() always returns None,
    save() silently discards data.
    """

    def load(self, key: str) -> dict[str, object] | None:  # noqa: ARG002
        """Always returns None — no state persisted."""
        return None

    def save(self, key: str, data: dict[str, object]) -> None:  # noqa: ARG002
        """Silently discards data — no-op."""


class FakeStorage:
    """Test double for StateStoragePort.

    Stores state in an in-memory dict. Useful for unit tests
    where you need to inspect saved state or pre-load state.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, object]] = {}

    def load(self, key: str) -> dict[str, object] | None:
        """Return a deep copy of stored state, or None if absent."""
        value = self._store.get(key)
        return copy.deepcopy(value) if value is not None else None

    def save(self, key: str, data: dict[str, object]) -> None:
        """Store a deep copy of data, preventing mutation leakage."""
        self._store[key] = copy.deepcopy(data)
