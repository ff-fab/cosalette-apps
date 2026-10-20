"""Hardware port for geiger2mqtt.

The handler depends only on this Protocol; cosalette injects the gpiozero
adapter in production and the fake adapter in dry-run mode.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self


class PulseCounterPort(Protocol):
    """Monotonic timestamps of the pulses counted since the adapter started.

    All times come from the adapter's own monotonic clock, so callers compare
    them only with :meth:`now` and :attr:`started_at`.
    """

    @property
    def started_at(self) -> float:
        """Clock time at which counting began (set on context entry)."""
        ...

    def now(self) -> float:
        """Return the current time of the adapter's clock."""
        ...

    def snapshot(self, since: float) -> list[float]:
        """Return the timestamps of all retained pulses later than ``since``."""
        ...

    def last_pulse(self) -> float | None:
        """Return the timestamp of the latest pulse, or None if none arrived."""
        ...

    async def __aenter__(self) -> Self:
        """Start counting."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop counting and release the hardware."""
        ...
