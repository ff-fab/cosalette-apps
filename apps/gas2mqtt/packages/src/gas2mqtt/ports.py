"""Hardware adapter ports for gas2mqtt.

Defines Protocol classes for hardware interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MagneticReading:
    """A single reading from the magnetometer.

    Attributes:
        bx: Magnetic field strength on X axis (raw sensor units).
        by: Magnetic field strength on Y axis (raw sensor units).
        bz: Magnetic field strength on Z axis (raw sensor units).
        temperature_raw: Raw temperature sensor value.
    """

    bx: int
    by: int
    bz: int
    temperature_raw: int


class MagnetometerPort(Protocol):
    """Port for reading a 3-axis magnetometer with temperature sensor.

    Implementations must provide magnetic field readings (bx, by, bz)
    and raw temperature values. The QMC5883L adapter reads from I2C;
    the fake adapter returns configurable values for testing/dry-run.
    """

    def read(self) -> MagneticReading:
        """Read magnetic field and temperature from the sensor.

        Pre-condition:
            ``initialize()`` must have been called first.

        Returns:
            MagneticReading with bx, by, bz, and temperature_raw values.

        Raises:
            IOError: If the I2C bus communication fails.
        """
        ...

    def initialize(self) -> None:
        """Initialize the sensor with configuration registers.

        Must be called before the first read(). Typically called
        during application lifespan startup.
        """
        ...

    def close(self) -> None:
        """Release hardware resources (close I2C bus).

        Called during application lifespan shutdown.
        """
        ...


class StateStoragePort(Protocol):
    """Port for persisting device state between app restarts.

    Implementations store and retrieve key-value state data.
    Keys are typically device names (e.g., "gas_counter").
    Values are JSON-serializable dicts.
    """

    def load(self, key: str) -> dict[str, object] | None:
        """Load saved state for the given key.

        Returns:
            The saved state dict, or None if no state exists.
        """
        ...

    def save(self, key: str, data: dict[str, object]) -> None:
        """Save state for the given key.

        Args:
            key: Identifier (typically device name).
            data: JSON-serializable state dict.
        """
        ...
