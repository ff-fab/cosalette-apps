"""Fake magnetometer adapter for testing and dry-run mode.

Provides deterministic readings for unit tests and --dry-run operation.
The bz value can be controlled to simulate trigger events.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

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

    async def __aenter__(self) -> Self:
        """Enter async context: initialize the fake sensor."""
        self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: close the fake sensor."""
        self.close()
