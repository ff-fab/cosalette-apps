"""Fake GPIO adapter for testing and dry-run mode.

Records all GPIO interactions without touching hardware.
Use in unit tests to verify button press sequences and timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Self


@dataclass
class PressCall:
    """Record of a single press() invocation."""

    pin: int
    duration: float


class FakeGpio:
    """Test double for GpioSwitchPort.

    Records all interactions for assertion in tests.

    Attributes:
        presses: List of all press() calls in order.
        initialized_pins: Pins passed to initialize().
        is_initialized: Whether initialize() was called.
        is_closed: Whether cleanup() was called.
    """

    def __init__(self) -> None:
        self.presses: list[PressCall] = []
        self.initialized_pins: list[int] = []
        self.is_initialized: bool = False
        self.is_closed: bool = False

    def initialize(self, pins: list[int]) -> None:
        """Record pin initialization."""
        self.initialized_pins = list(pins)
        self.is_initialized = True

    async def press(self, pin: int, duration: float) -> None:
        """Record a button press without any delay."""
        self.presses.append(PressCall(pin=pin, duration=duration))

    def cleanup(self) -> None:
        """Record cleanup."""
        self.is_closed = True

    async def __aenter__(self) -> Self:
        """Enter async context: record initialization."""
        self.initialize(self.initialized_pins)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: record cleanup."""
        self.cleanup()
