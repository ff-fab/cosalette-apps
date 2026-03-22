"""Unit tests for CalibrationStateMachine.

Test Techniques Used:
- State Transition Testing: IDLE -> READY -> TIMING -> READY/COMPLETE lifecycle
- Boundary Value Analysis: Single run, varying measurements
- Specification-based Testing: Direction alternation, average computation
- Error Guessing: Invalid transitions from each state
"""

import pytest

from velux2mqtt.domain.calibration import (
    CalibrationDirection,
    CalibrationError,
    CalibrationState,
    CalibrationStateMachine,
)


class FakeClock:
    """Manually-advanced clock for deterministic timing tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sm(clock: FakeClock) -> CalibrationStateMachine:
    return CalibrationStateMachine(time_source=clock)


# -- Happy path: full 3-run calibration ------------------------------------


class TestFullCalibration:
    """Full multi-run calibration through all states."""

    def test_three_run_calibration(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Complete 3-run calibration records 3 close and 3 open durations."""
        sm.start(runs=3)
        assert sm.state is CalibrationState.READY
        assert sm.current_run == 1

        close_times = [10.0, 11.0, 12.0]
        open_times = [9.0, 10.0, 11.0]

        for run in range(3):
            # Close phase
            assert sm.direction is CalibrationDirection.CLOSE
            event = sm.go()
            assert event.press_button is True
            assert event.direction is CalibrationDirection.CLOSE
            assert sm.state is CalibrationState.TIMING

            clock.advance(close_times[run])
            event = sm.mark()
            assert sm.state is CalibrationState.READY
            assert sm.direction is CalibrationDirection.OPEN

            # Open phase
            event = sm.go()
            assert event.press_button is True
            assert event.direction is CalibrationDirection.OPEN

            clock.advance(open_times[run])
            event = sm.mark()

            if run < 2:
                assert sm.state is CalibrationState.READY
                assert sm.current_run == run + 2
            else:
                assert sm.state is CalibrationState.COMPLETE

        assert sm.average_close == pytest.approx(11.0)
        assert sm.average_open == pytest.approx(10.0)


# -- Direction alternation --------------------------------------------------


class TestDirectionAlternation:
    """Verify close/open alternation within and across runs."""

    def test_first_direction_is_close(self, sm: CalibrationStateMachine) -> None:
        """Calibration always starts with close direction."""
        sm.start(runs=1)
        assert sm.direction is CalibrationDirection.CLOSE

    def test_alternates_within_run(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """After close measurement, direction switches to open."""
        sm.start(runs=1)
        sm.go()
        clock.advance(5.0)
        sm.mark()
        assert sm.direction is CalibrationDirection.OPEN

    def test_resets_to_close_on_new_run(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """New run starts with close direction again."""
        sm.start(runs=2)

        # Run 1: close then open
        sm.go()
        clock.advance(5.0)
        sm.mark()
        sm.go()
        clock.advance(5.0)
        sm.mark()

        # Run 2 should start with close
        assert sm.current_run == 2
        assert sm.direction is CalibrationDirection.CLOSE


# -- Average computation ---------------------------------------------------


class TestAverageComputation:
    """Verify average duration calculations."""

    def test_averages_with_varying_durations(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Averages correctly computed from varying measurements."""
        sm.start(runs=2)

        # Run 1: close=8, open=6
        sm.go()
        clock.advance(8.0)
        sm.mark()
        sm.go()
        clock.advance(6.0)
        sm.mark()

        # Run 2: close=12, open=14
        sm.go()
        clock.advance(12.0)
        sm.mark()
        sm.go()
        clock.advance(14.0)
        sm.mark()

        assert sm.average_close == pytest.approx(10.0)
        assert sm.average_open == pytest.approx(10.0)

    def test_average_close_no_data_raises(self, sm: CalibrationStateMachine) -> None:
        """Accessing average_close without data raises CalibrationError."""
        with pytest.raises(CalibrationError, match="no close measurements"):
            _ = sm.average_close

    def test_average_open_no_data_raises(self, sm: CalibrationStateMachine) -> None:
        """Accessing average_open without data raises CalibrationError."""
        with pytest.raises(CalibrationError, match="no open measurements"):
            _ = sm.average_open


# -- Cancel from each state ------------------------------------------------


class TestCancel:
    """Cancel returns to IDLE from any non-IDLE state."""

    def test_cancel_from_ready(self, sm: CalibrationStateMachine) -> None:
        sm.start(runs=1)
        assert sm.state is CalibrationState.READY

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_timing(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        sm.start(runs=1)
        sm.go()
        assert sm.state is CalibrationState.TIMING

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_complete(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        sm.start(runs=1)
        sm.go()
        clock.advance(5.0)
        sm.mark()
        sm.go()
        clock.advance(5.0)
        sm.mark()
        assert sm.state is CalibrationState.COMPLETE

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_idle_is_noop(self, sm: CalibrationStateMachine) -> None:
        """Cancel from IDLE stays in IDLE (idempotent)."""
        sm.cancel()
        assert sm.state is CalibrationState.IDLE


# -- Invalid transitions ---------------------------------------------------


class TestInvalidTransitions:
    """Invalid transitions raise CalibrationError with clear messages."""

    def test_go_from_idle(self, sm: CalibrationStateMachine) -> None:
        """Cannot go() without starting calibration."""
        with pytest.raises(CalibrationError, match="cannot go.*IDLE"):
            sm.go()

    def test_mark_from_idle(self, sm: CalibrationStateMachine) -> None:
        """Cannot mark() without timing."""
        with pytest.raises(CalibrationError, match="cannot mark.*IDLE"):
            sm.mark()

    def test_mark_from_ready(self, sm: CalibrationStateMachine) -> None:
        """Cannot mark() before go()."""
        sm.start(runs=1)
        with pytest.raises(CalibrationError, match="cannot mark.*READY"):
            sm.mark()

    def test_go_from_timing(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cannot go() while already timing."""
        sm.start(runs=1)
        sm.go()
        with pytest.raises(CalibrationError, match="cannot go.*TIMING"):
            sm.go()

    def test_start_from_ready(self, sm: CalibrationStateMachine) -> None:
        """Cannot start() if already started."""
        sm.start(runs=1)
        with pytest.raises(CalibrationError, match="cannot start.*READY"):
            sm.start(runs=1)

    def test_start_from_complete(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cannot start() from COMPLETE — must cancel() first."""
        sm.start(runs=1)
        sm.go()
        clock.advance(5.0)
        sm.mark()
        sm.go()
        clock.advance(5.0)
        sm.mark()
        assert sm.state is CalibrationState.COMPLETE

        with pytest.raises(CalibrationError, match="cannot start.*COMPLETE"):
            sm.start(runs=1)


# -- Edge cases -------------------------------------------------------------


class TestEdgeCases:
    """Boundary and edge case scenarios."""

    def test_single_run(self, sm: CalibrationStateMachine, clock: FakeClock) -> None:
        """Single run produces one close and one open measurement."""
        sm.start(runs=1)

        sm.go()
        clock.advance(7.5)
        sm.mark()

        sm.go()
        clock.advance(8.5)
        sm.mark()

        assert sm.state is CalibrationState.COMPLETE
        assert sm.average_close == pytest.approx(7.5)
        assert sm.average_open == pytest.approx(8.5)

    def test_runs_less_than_one_raises(self, sm: CalibrationStateMachine) -> None:
        """start(runs=0) raises ValueError."""
        with pytest.raises(ValueError, match="runs must be >= 1"):
            sm.start(runs=0)

    def test_current_run_is_zero_when_idle(self, sm: CalibrationStateMachine) -> None:
        """current_run reports 0 when not calibrating."""
        assert sm.current_run == 0

    def test_restart_after_cancel(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Can start a fresh calibration after cancel."""
        sm.start(runs=1)
        sm.go()
        clock.advance(5.0)
        sm.cancel()

        # Should be able to start again
        sm.start(runs=2)
        assert sm.state is CalibrationState.READY
        assert sm.total_runs == 2
        assert sm.current_run == 1

    def test_go_event_contains_direction(self, sm: CalibrationStateMachine) -> None:
        """go() event includes the current direction."""
        sm.start(runs=1)
        event = sm.go()
        assert event.direction is CalibrationDirection.CLOSE
        assert event.press_button is True

    def test_start_event_has_no_button_press(self, sm: CalibrationStateMachine) -> None:
        """start() event does not request a button press."""
        event = sm.start(runs=1)
        assert event.press_button is False
        assert event.direction is CalibrationDirection.CLOSE
