"""Hardware adapter ports for wallpanel-control.

Defines Protocol classes for hardware interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.

WallpanelPort abstracts SSH-based control of the wallpanel (brightness,
screen power, system power). WolPort abstracts Wake-on-LAN packet
sending. Neither protocol exposes transport details.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable


@runtime_checkable
class WallpanelPort(Protocol):
    """Port for controlling a wall-mounted panel via SSH.

    Abstracts brightness control (sysfs backlight), screen power
    (D-Bus Mutter PowerSaveMode), and system power management
    (systemctl hibernate/suspend).

    Methods that interact with the wallpanel distinguish between
    'unreachable' (return None — normal when hibernating) and
    'unexpected error' (raise — framework handles via error topic).

    Implementations must support async context manager lifecycle
    for connection management.
    """

    async def set_brightness(self, value: int) -> None:
        """Set backlight brightness (raw sysfs value).

        Args:
            value: Raw brightness value to write to sysfs.

        Raises:
            Exception: On unexpected communication failure.
        """
        ...

    async def get_brightness(self) -> int | None:
        """Read current backlight brightness from sysfs.

        Returns:
            Current brightness value, or None if wallpanel is unreachable.
        """
        ...

    async def get_max_brightness(self) -> int:
        """Read maximum brightness from sysfs.

        Called once at startup to determine the brightness range.

        Returns:
            Maximum brightness value.
        """
        ...

    async def screen_on(self) -> None:
        """Turn display on via D-Bus (Mutter PowerSaveMode=0).

        Raises:
            Exception: On unexpected communication failure.
        """
        ...

    async def screen_off(self) -> None:
        """Turn display off via D-Bus (Mutter PowerSaveMode=1).

        Raises:
            Exception: On unexpected communication failure.
        """
        ...

    async def get_screen_state(self) -> bool | None:
        """Read current display power state via D-Bus.

        Returns:
            True if screen is on, False if off, None if unreachable.
        """
        ...

    async def hibernate(self) -> None:
        """Send 'systemctl hibernate' command.

        Raises:
            Exception: On unexpected communication failure.
        """
        ...

    async def suspend(self) -> None:
        """Send 'systemctl suspend' command.

        Raises:
            Exception: On unexpected communication failure.
        """
        ...

    async def is_reachable(self) -> bool:
        """Quick connectivity check (e.g. SSH connect + disconnect).

        Returns:
            True if wallpanel is reachable, False otherwise.
        """
        ...

    async def __aenter__(self) -> Self:
        """Enter async context: establish connection.

        Enables cosalette adapter lifecycle management via
        ``AsyncExitStack``.
        """
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: close connection and release resources."""
        ...


@runtime_checkable
class WolPort(Protocol):
    """Port for sending Wake-on-LAN magic packets.

    Abstracts the UDP broadcast mechanism so production and test
    implementations can be swapped via cosalette's adapter registry.
    """

    async def wake(self, mac: str, broadcast: str) -> None:
        """Send a Wake-on-LAN magic packet.

        Args:
            mac: MAC address of the target device.
            broadcast: Broadcast address for the magic packet.
        """
        ...
