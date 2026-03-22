"""Position tracking — time-based estimation for Velux covers.

Since there is no position feedback sensor, position is estimated
from travel time. Positions use Home Assistant semantics:
0 = fully closed (down), 100 = fully open (up).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto


class MovementState(Enum):
    """Current movement state of a cover."""

    STOPPED = auto()
    OPENING = auto()
    CLOSING = auto()


@dataclass
class PositionTracker:
    """Estimates cover position from travel time.

    Attributes:
        position: Current estimated position (0–100).
        state: Current movement state.
    """

    travel_duration_up: float
    travel_duration_down: float
    travel_time_offset: float = 1.0
    time_source: Callable[[], float] = field(default=time.perf_counter)

    position: float = field(default=0.0, init=False)
    state: MovementState = field(default=MovementState.STOPPED, init=False)
    _move_start_time: float | None = field(default=None, init=False, repr=False)

    def start_opening(self) -> None:
        """Begin opening movement (toward 100%).

        If currently closing, stops first and updates position.
        """
        if self.state == MovementState.CLOSING:
            self._apply_elapsed()
        self.state = MovementState.OPENING
        self._move_start_time = self.time_source()

    def start_closing(self) -> None:
        """Begin closing movement (toward 0%).

        If currently opening, stops first and updates position.
        """
        if self.state == MovementState.OPENING:
            self._apply_elapsed()
        self.state = MovementState.CLOSING
        self._move_start_time = self.time_source()

    def stop(self) -> None:
        """Stop movement and update estimated position."""
        if self.state != MovementState.STOPPED:
            self._apply_elapsed()
        self.state = MovementState.STOPPED
        self._move_start_time = None

    def finalize_open(self) -> None:
        """Set position to 100% (fully open) after full travel."""
        self.position = 100.0
        self.state = MovementState.STOPPED
        self._move_start_time = None

    def finalize_closed(self) -> None:
        """Set position to 0% (fully closed) after full travel."""
        self.position = 0.0
        self.state = MovementState.STOPPED
        self._move_start_time = None

    def travel_time_for(self, current: float, target: int) -> float:
        """Calculate travel time to reach target from current position.

        Args:
            current: Current position (0–100).
            target: Target position (0–100).

        Returns:
            Seconds of travel time needed (includes offset).
        """
        delta = abs(current - target) / 100.0
        if target > current:
            return delta * self.travel_duration_up + self.travel_time_offset
        return delta * self.travel_duration_down + self.travel_time_offset

    @property
    def position_int(self) -> int:
        """Current position rounded to integer (0–100)."""
        return round(self._clamped(self.position))

    def _apply_elapsed(self) -> None:
        """Update position based on elapsed time since movement started."""
        if self._move_start_time is None:
            return
        elapsed = self.time_source() - self._move_start_time
        effective = max(0.0, elapsed - self.travel_time_offset)

        if self.state == MovementState.OPENING:
            fraction = effective / self.travel_duration_up
            self.position += fraction * 100.0
        elif self.state == MovementState.CLOSING:
            fraction = effective / self.travel_duration_down
            self.position -= fraction * 100.0

        self.position = self._clamped(self.position)
        self._move_start_time = None

    @staticmethod
    def _clamped(value: float) -> float:
        """Clamp value to [0, 100]."""
        return max(0.0, min(100.0, value))
