"""Protocol ports for jeelink2mqtt hardware abstraction.

Follows hexagonal architecture (ADR-003): device code depends on
Protocol ports, never on concrete implementations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from jeelink2mqtt.models import SensorMapping, SensorReading


@runtime_checkable
class JeeLinkPort(Protocol):
    """Hardware abstraction for the JeeLink USB receiver.

    Concrete implementations wrap the serial connection and frame
    parsing.  Application code depends only on this protocol, making
    it straightforward to substitute a mock or simulator for testing.
    """

    def open(self) -> None:
        """Open the serial connection to the JeeLink receiver."""
        ...

    def close(self) -> None:
        """Close the serial connection."""
        ...

    def start_scan(self) -> None:
        """Start scanning for incoming LaCrosse sensor frames."""
        ...

    def stop_scan(self) -> None:
        """Stop scanning for sensor frames."""
        ...

    def register_callback(self, callback: Callable[[SensorReading], None]) -> None:
        """Register a callback invoked for each decoded sensor frame.

        Args:
            callback: Function called with a :class:`SensorReading`
                each time a valid frame is received.
        """
        ...

    def set_led(self, enabled: bool) -> None:
        """Control the JeeLink on-board LED.

        Args:
            enabled: ``True`` to turn the LED on, ``False`` to turn it off.
        """
        ...


@runtime_checkable
class SensorRegistryPort(Protocol):
    """Read-only access to the sensor ID → name registry.

    Used by telemetry-reading code to resolve ephemeral LaCrosse IDs
    to stable logical names and to check liveness.  Write operations
    (adopt, assign, reset) live on the concrete registry implementation.
    """

    def resolve(self, sensor_id: int) -> str | None:
        """Resolve an ephemeral sensor ID to a logical name.

        Returns:
            The sensor name, or ``None`` if the ID is unmapped.
        """
        ...

    def is_stale(self, sensor_name: str) -> bool:
        """Check whether a sensor has exceeded its staleness timeout.

        Args:
            sensor_name: Logical sensor name.

        Returns:
            ``True`` if the sensor hasn't reported within the timeout.
        """
        ...

    def get_mapping(self, sensor_name: str) -> SensorMapping | None:
        """Get the current mapping for a logical sensor name.

        Returns:
            The active :class:`SensorMapping`, or ``None`` if unmapped.
        """
        ...

    def get_all_mappings(self) -> dict[str, SensorMapping]:
        """Get all active mappings.

        Returns:
            Dictionary of ``{sensor_name: SensorMapping}``.
        """
        ...

    def get_unmapped_ids(self) -> dict[int, SensorReading]:
        """Get recently-seen sensor IDs that are not yet mapped.

        Returns:
            Dictionary of ``{sensor_id: last_SensorReading}``.
        """
        ...
