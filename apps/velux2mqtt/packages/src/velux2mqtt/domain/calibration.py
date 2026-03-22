"""Calibration state machine — timed measurement of cover travel durations.

Guides the user through a multi-run calibration procedure that alternates
between close and open directions, timing each traversal.  Each direction
pass has two marks: the first records the motor start lag (offset), the
second records the actual travel duration.  On completion the machine
provides averaged durations per direction and the average offset.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto


class CalibrationState(Enum):
    """States of the calibration procedure."""

    IDLE = auto()
    READY = auto()
    TIMING_OFFSET = auto()
    TIMING = auto()
    COMPLETE = auto()


class CalibrationDirection(Enum):
    """Direction being timed."""

    CLOSE = auto()
    OPEN = auto()


class CalibrationError(Exception):
    """Raised on invalid state transitions."""


@dataclass(frozen=True, slots=True)
class CalibrationEvent:
    """Action the device handler should perform after a transition.

    Attributes:
        press_button: True when the handler should trigger a button press.
        direction: Direction of the movement (present when relevant).
    """

    press_button: bool = False
    direction: CalibrationDirection | None = None


@dataclass
class CalibrationStateMachine:
    """Manages a timed calibration procedure for a single cover.

    Usage::

        sm = CalibrationStateMachine()
        sm.start(runs=3)       # IDLE -> READY (run 1/3, direction=close)
        sm.go()                # READY -> TIMING_OFFSET (starts timer, press event)
        sm.mark()              # TIMING_OFFSET -> TIMING (records offset)
        sm.mark()              # TIMING -> READY|COMPLETE (records travel)

    Args:
        time_source: Callable returning monotonic seconds (injectable for tests).
    """

    time_source: Callable[[], float] = field(default=time.perf_counter)

    state: CalibrationState = field(default=CalibrationState.IDLE, init=False)
    _total_runs: int = field(default=0, init=False, repr=False)
    _current_run: int = field(default=0, init=False, repr=False)
    _direction: CalibrationDirection = field(
        default=CalibrationDirection.CLOSE, init=False, repr=False
    )
    _start_time: float | None = field(default=None, init=False, repr=False)
    _close_durations: list[float] = field(default_factory=list, init=False, repr=False)
    _open_durations: list[float] = field(default_factory=list, init=False, repr=False)
    _offset_durations: list[float] = field(default_factory=list, init=False, repr=False)

    # -- public transitions --------------------------------------------------

    def start(self, runs: int = 3) -> CalibrationEvent:
        """Begin calibration: move to READY for the first run.

        Args:
            runs: Number of close/open measurement cycles to perform.

        Returns:
            Event indicating readiness (no button press yet).

        Raises:
            CalibrationError: If not in IDLE state.
            ValueError: If *runs* < 1.
        """
        self._require_state(CalibrationState.IDLE, "start")
        if runs < 1:
            msg = f"runs must be >= 1, got {runs}"
            raise ValueError(msg)

        self._total_runs = runs
        self._current_run = 1
        self._direction = CalibrationDirection.CLOSE
        self._close_durations.clear()
        self._open_durations.clear()
        self._offset_durations.clear()
        self.state = CalibrationState.READY
        return CalibrationEvent(direction=self._direction)

    def go(self) -> CalibrationEvent:
        """Trigger a button press and start timing.

        Returns:
            Event requesting a button press with the current direction.

        Raises:
            CalibrationError: If not in READY state.
        """
        self._require_state(CalibrationState.READY, "go")
        self._start_time = self.time_source()
        self.state = CalibrationState.TIMING_OFFSET
        return CalibrationEvent(press_button=True, direction=self._direction)

    def mark(self) -> CalibrationEvent:
        """Record a measurement mark.

        In TIMING_OFFSET state: records the motor start lag (offset) and
        transitions to TIMING to continue measuring the travel duration.

        In TIMING state: records the travel duration, then either advances
        to the next direction/run or transitions to COMPLETE.

        Returns:
            Event describing the next expected action.

        Raises:
            CalibrationError: If not in TIMING_OFFSET or TIMING state.
        """
        if self.state is CalibrationState.TIMING_OFFSET:
            return self._mark_offset()
        if self.state is CalibrationState.TIMING:
            return self._mark_travel()

        msg = f"cannot mark() in {self.state.name} state"
        raise CalibrationError(msg)

    def _mark_offset(self) -> CalibrationEvent:
        """Record offset duration and transition to TIMING."""
        assert self._start_time is not None  # noqa: S101 — guaranteed by state
        elapsed = self.time_source() - self._start_time
        self._offset_durations.append(elapsed)
        self._start_time = self.time_source()
        self.state = CalibrationState.TIMING
        return CalibrationEvent(direction=self._direction)

    def _mark_travel(self) -> CalibrationEvent:
        """Record travel duration and advance to next step."""
        assert self._start_time is not None  # noqa: S101 — guaranteed by state
        elapsed = self.time_source() - self._start_time
        self._start_time = None

        if self._direction is CalibrationDirection.CLOSE:
            self._close_durations.append(elapsed)
        else:
            self._open_durations.append(elapsed)

        return self._advance()

    def cancel(self) -> CalibrationEvent:
        """Abort calibration and return to IDLE from any state.

        Returns:
            Event with no action required.
        """
        self.state = CalibrationState.IDLE
        self._start_time = None
        self._total_runs = 0
        self._current_run = 0
        self._direction = CalibrationDirection.CLOSE
        self._close_durations.clear()
        self._open_durations.clear()
        self._offset_durations.clear()
        return CalibrationEvent()

    # -- query helpers --------------------------------------------------------

    @property
    def current_run(self) -> int:
        """Current run number (1-based), 0 when IDLE."""
        return self._current_run if self.state is not CalibrationState.IDLE else 0

    @property
    def total_runs(self) -> int:
        """Total configured runs."""
        return self._total_runs

    @property
    def direction(self) -> CalibrationDirection:
        """Direction being (or about to be) measured."""
        return self._direction

    @property
    def average_close(self) -> float:
        """Average close duration in seconds.

        Raises:
            CalibrationError: If no close measurements recorded.
        """
        if not self._close_durations:
            msg = "no close measurements recorded"
            raise CalibrationError(msg)
        return sum(self._close_durations) / len(self._close_durations)

    @property
    def average_open(self) -> float:
        """Average open duration in seconds.

        Raises:
            CalibrationError: If no open measurements recorded.
        """
        if not self._open_durations:
            msg = "no open measurements recorded"
            raise CalibrationError(msg)
        return sum(self._open_durations) / len(self._open_durations)

    @property
    def average_offset(self) -> float:
        """Average motor start/stop lag (offset) in seconds.

        Raises:
            CalibrationError: If no offset measurements recorded.
        """
        if not self._offset_durations:
            msg = "no offset measurements recorded"
            raise CalibrationError(msg)
        return sum(self._offset_durations) / len(self._offset_durations)

    # -- internals ------------------------------------------------------------

    def _advance(self) -> CalibrationEvent:
        """Determine next state after a measurement."""
        if self._direction is CalibrationDirection.CLOSE:
            # After close, always do open in the same run
            self._direction = CalibrationDirection.OPEN
            self.state = CalibrationState.READY
            return CalibrationEvent(direction=self._direction)

        # After open, advance to next run or complete
        if self._current_run < self._total_runs:
            self._current_run += 1
            self._direction = CalibrationDirection.CLOSE
            self.state = CalibrationState.READY
            return CalibrationEvent(direction=self._direction)

        self.state = CalibrationState.COMPLETE
        return CalibrationEvent()

    def _require_state(self, expected: CalibrationState, action: str) -> None:
        """Raise CalibrationError if current state doesn't match."""
        if self.state is not expected:
            msg = f"cannot {action}() in {self.state.name} state"
            raise CalibrationError(msg)
