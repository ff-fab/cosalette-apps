"""Hardware adapter ports for velux2mqtt.

Defines Protocol classes for hardware interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self


class GpioSwitchPort(Protocol):
    """Port for controlling GPIO-driven analog switches.

    Each M74HC4066 analog switch is controlled by a single GPIO pin:
    HIGH closes the switch (simulating a button press), LOW opens it.

    Implementations must handle pin initialization (all pins OUTPUT,
    initially LOW) and cleanup (all pins LOW, resources released).
    """

    async def press(self, pin: int, duration: float) -> None:
        """Simulate a button press by pulsing a GPIO pin HIGH.

        Sets the pin HIGH, waits for ``duration`` seconds, then sets
        it LOW. Uses ``asyncio.sleep`` for the hold period.

        Args:
            pin: BCM GPIO pin number.
            duration: Seconds to hold the pin HIGH.
        """
        ...

    def initialize(self, pins: list[int]) -> None:
        """Configure GPIO pins as outputs with initial LOW state.

        Must be called before any ``press()`` call. Called automatically
        by ``__aenter__`` during adapter lifecycle entry.

        Args:
            pins: List of BCM GPIO pin numbers to initialize.
        """
        ...

    def cleanup(self) -> None:
        """Release all GPIO resources.

        Sets all pins LOW and releases the underlying GPIO devices.
        Called automatically by ``__aexit__`` during adapter lifecycle
        teardown.
        """
        ...

    async def __aenter__(self) -> Self:
        """Enter async context: initialize GPIO pins.

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
        """Exit async context: release GPIO resources."""
        ...
