"""Unit tests for CalibrationStateMachine.

Test Techniques Used:
- State Transition Testing: IDLE -> READY -> TIMING_OFFSET -> TIMING -> READY/COMPLETE,
  including TIMING_DEAD_BAND when measure_dead_band=True
- Boundary Value Analysis: Single run, varying measurements
- Specification-based Testing: Direction alternation, average computation, offset,
  dead band percentage calculation
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


def _do_direction(
    sm: CalibrationStateMachine,
    clock: FakeClock,
    offset: float,
    travel: float,
) -> None:
    """Helper: go -> mark (offset) -> mark (travel) for one direction."""
    sm.go()
    clock.advance(offset)
    sm.mark()  # records offset, transitions to TIMING
    clock.advance(travel)
    sm.mark()  # records travel, advances


# -- Happy path: full 3-run calibration ------------------------------------


class TestFullCalibration:
    """Full multi-run calibration through all states."""

    def test_three_run_calibration(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Complete 3-run calibration records 3 close, 3 open, and 6 offset durations."""
        sm.start(runs=3)
        assert sm.state is CalibrationState.READY
        assert sm.current_run == 1

        close_times = [10.0, 11.0, 12.0]
        open_times = [9.0, 10.0, 11.0]
        offset_time = 0.5

        for run in range(3):
            # Close phase: go -> mark(offset) -> mark(travel)
            assert sm.direction is CalibrationDirection.CLOSE
            event = sm.go()
            assert event.press_button is True
            assert event.direction is CalibrationDirection.CLOSE
            assert sm.state is CalibrationState.TIMING_OFFSET

            clock.advance(offset_time)
            event = sm.mark()  # offset mark
            assert sm.state is CalibrationState.TIMING
            assert event.direction is CalibrationDirection.CLOSE

            clock.advance(close_times[run])
            event = sm.mark()  # travel mark
            assert sm.state is CalibrationState.READY
            assert sm.direction is CalibrationDirection.OPEN

            # Open phase: go -> mark(offset) -> mark(travel)
            event = sm.go()
            assert event.press_button is True
            assert event.direction is CalibrationDirection.OPEN

            clock.advance(offset_time)
            sm.mark()  # offset mark

            clock.advance(open_times[run])
            event = sm.mark()  # travel mark

            if run < 2:
                assert sm.state is CalibrationState.READY
                assert sm.current_run == run + 2
            else:
                assert sm.state is CalibrationState.COMPLETE

        assert sm.average_close == pytest.approx(11.0)
        assert sm.average_open == pytest.approx(10.0)
        assert sm.average_offset == pytest.approx(0.5)


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
        _do_direction(sm, clock, offset=0.3, travel=5.0)
        assert sm.direction is CalibrationDirection.OPEN

    def test_resets_to_close_on_new_run(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """New run starts with close direction again."""
        sm.start(runs=2)

        # Run 1: close then open
        _do_direction(sm, clock, offset=0.3, travel=5.0)
        _do_direction(sm, clock, offset=0.3, travel=5.0)

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

        # Run 1: close=8, open=6, offsets=0.4
        _do_direction(sm, clock, offset=0.4, travel=8.0)
        _do_direction(sm, clock, offset=0.4, travel=6.0)

        # Run 2: close=12, open=14, offsets=0.6
        _do_direction(sm, clock, offset=0.6, travel=12.0)
        _do_direction(sm, clock, offset=0.6, travel=14.0)

        assert sm.average_close == pytest.approx(10.0)
        assert sm.average_open == pytest.approx(10.0)
        assert sm.average_offset == pytest.approx(0.5)

    def test_average_close_no_data_raises(self, sm: CalibrationStateMachine) -> None:
        """Accessing average_close without data raises CalibrationError."""
        with pytest.raises(CalibrationError, match="no close measurements"):
            _ = sm.average_close

    def test_average_open_no_data_raises(self, sm: CalibrationStateMachine) -> None:
        """Accessing average_open without data raises CalibrationError."""
        with pytest.raises(CalibrationError, match="no open measurements"):
            _ = sm.average_open

    def test_average_offset_no_data_raises(self, sm: CalibrationStateMachine) -> None:
        """Accessing average_offset without data raises CalibrationError."""
        with pytest.raises(CalibrationError, match="no offset measurements"):
            _ = sm.average_offset


# -- Cancel from each state ------------------------------------------------


class TestCancel:
    """Cancel returns to IDLE from any non-IDLE state."""

    def test_cancel_from_ready(self, sm: CalibrationStateMachine) -> None:
        sm.start(runs=1)
        assert sm.state is CalibrationState.READY

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_timing_offset(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cancel from TIMING_OFFSET returns to IDLE."""
        sm.start(runs=1)
        sm.go()
        assert sm.state is CalibrationState.TIMING_OFFSET

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_timing(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset -> TIMING
        assert sm.state is CalibrationState.TIMING

        sm.cancel()
        assert sm.state is CalibrationState.IDLE

    def test_cancel_from_complete(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        sm.start(runs=1)
        _do_direction(sm, clock, offset=0.3, travel=5.0)
        _do_direction(sm, clock, offset=0.3, travel=5.0)
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

    def test_go_from_timing_offset(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cannot go() while in TIMING_OFFSET."""
        sm.start(runs=1)
        sm.go()
        with pytest.raises(CalibrationError, match="cannot go.*TIMING_OFFSET"):
            sm.go()

    def test_go_from_timing(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cannot go() while in TIMING."""
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset -> TIMING
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
        _do_direction(sm, clock, offset=0.3, travel=5.0)
        _do_direction(sm, clock, offset=0.3, travel=5.0)
        assert sm.state is CalibrationState.COMPLETE

        with pytest.raises(CalibrationError, match="cannot start.*COMPLETE"):
            sm.start(runs=1)


# -- Offset-specific tests -------------------------------------------------


class TestOffsetMeasurement:
    """Verify the TIMING_OFFSET -> TIMING transition and offset recording."""

    def test_go_transitions_to_timing_offset(self, sm: CalibrationStateMachine) -> None:
        """go() transitions from READY to TIMING_OFFSET."""
        sm.start(runs=1)
        event = sm.go()
        assert sm.state is CalibrationState.TIMING_OFFSET
        assert event.press_button is True

    def test_first_mark_records_offset_and_transitions_to_timing(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """First mark() in TIMING_OFFSET records offset, goes to TIMING.

        Technique: State Transition Testing — TIMING_OFFSET -> TIMING.
        """
        sm.start(runs=1)
        sm.go()
        clock.advance(0.8)
        event = sm.mark()

        assert sm.state is CalibrationState.TIMING
        assert event.press_button is False
        assert event.direction is CalibrationDirection.CLOSE

    def test_offset_event_has_no_button_press(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Offset mark event does not request a button press."""
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        event = sm.mark()
        assert event.press_button is False

    def test_offset_measured_separately_from_travel(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Offset and travel durations are independent measurements.

        Technique: Specification-based — offset timer resets for travel.
        """
        sm.start(runs=1)
        sm.go()
        clock.advance(0.7)
        sm.mark()  # offset = 0.7

        clock.advance(5.0)
        sm.mark()  # close travel = 5.0

        # Open direction
        sm.go()
        clock.advance(0.9)
        sm.mark()  # offset = 0.9

        clock.advance(6.0)
        sm.mark()  # open travel = 6.0

        assert sm.average_offset == pytest.approx(0.8)  # (0.7 + 0.9) / 2
        assert sm.average_close == pytest.approx(5.0)
        assert sm.average_open == pytest.approx(6.0)

    def test_offset_cleared_on_cancel(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Cancel clears offset measurements.

        Technique: State Transition Testing — cancel clears all data.
        """
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # record one offset
        sm.cancel()

        with pytest.raises(CalibrationError, match="no offset measurements"):
            _ = sm.average_offset

    def test_offset_cleared_on_restart(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Restart after cancel clears offset data from previous attempt."""
        sm.start(runs=1)
        _do_direction(sm, clock, offset=1.0, travel=5.0)
        sm.cancel()
        sm.start(runs=1)

        with pytest.raises(CalibrationError, match="no offset measurements"):
            _ = sm.average_offset


# -- Edge cases -------------------------------------------------------------


class TestEdgeCases:
    """Boundary and edge case scenarios."""

    def test_single_run(self, sm: CalibrationStateMachine, clock: FakeClock) -> None:
        """Single run produces one close, one open, and two offset measurements."""
        sm.start(runs=1)

        _do_direction(sm, clock, offset=0.5, travel=7.5)
        _do_direction(sm, clock, offset=0.5, travel=8.5)

        assert sm.state is CalibrationState.COMPLETE
        assert sm.average_close == pytest.approx(7.5)
        assert sm.average_open == pytest.approx(8.5)
        assert sm.average_offset == pytest.approx(0.5)

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
        """Can start a fresh calibration after cancel; old data is cleared."""
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset
        clock.advance(5.0)
        sm.mark()  # close travel
        sm.cancel()

        # Stale data must be gone
        assert sm.total_runs == 0
        with pytest.raises(CalibrationError, match="no close measurements"):
            _ = sm.average_close

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


# -- Dead band measurement ---------------------------------------------------


def _do_direction_with_dead_band(
    sm: CalibrationStateMachine,
    clock: FakeClock,
    offset: float,
    dead_band: float,
    travel: float,
) -> None:
    """Helper: go -> mark(offset) -> mark(dead_band) -> mark(travel)."""
    sm.go()
    clock.advance(offset)
    sm.mark()  # records offset, transitions to TIMING_DEAD_BAND
    clock.advance(dead_band)
    sm.mark()  # records dead band, transitions to TIMING
    clock.advance(travel)
    sm.mark()  # records travel, advances


class TestDeadBandMeasurement:
    """Tests for calibration with measure_dead_band=True."""

    def test_offset_mark_transitions_to_timing_dead_band(
        self, clock: FakeClock
    ) -> None:
        """With measure_dead_band, offset mark goes to TIMING_DEAD_BAND.

        Technique: State Transition Testing — TIMING_OFFSET -> TIMING_DEAD_BAND.
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=1, measure_dead_band=True)
        sm.go()
        clock.advance(0.5)
        event = sm.mark()  # offset mark

        assert sm.state is CalibrationState.TIMING_DEAD_BAND
        assert event.direction is CalibrationDirection.CLOSE

    def test_dead_band_mark_transitions_to_timing(self, clock: FakeClock) -> None:
        """Dead band mark transitions to TIMING.

        Technique: State Transition Testing — TIMING_DEAD_BAND -> TIMING.
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=1, measure_dead_band=True)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset
        clock.advance(1.0)
        event = sm.mark()  # dead band

        assert sm.state is CalibrationState.TIMING
        assert event.direction is CalibrationDirection.CLOSE

    def test_full_calibration_with_dead_band(self, clock: FakeClock) -> None:
        """Complete single-run calibration with dead band records all measurements.

        Technique: Specification-based — full lifecycle with dead band.
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=1, measure_dead_band=True)

        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.0, travel=8.0)
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.2, travel=9.0)

        assert sm.state is CalibrationState.COMPLETE
        assert sm.average_close == pytest.approx(8.0)
        assert sm.average_open == pytest.approx(9.0)
        assert sm.average_offset == pytest.approx(0.5)
        assert sm.average_dead_band == pytest.approx(1.1)
        assert sm.has_dead_band is True

    def test_dead_band_pct_calculation(self, clock: FakeClock) -> None:
        """Dead band percentage computed from travel and dead band durations.

        Technique: Specification-based — percentage formula verification.

        With close=8s, open=9s, dead_band=1s per direction:
        avg_total = ((8+1) + (9+1)) / 2 = 9.5
        pct = 1.0 / 9.5 * 100 = 10.53%
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=1, measure_dead_band=True)

        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.0, travel=8.0)
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.0, travel=9.0)

        pct = sm.dead_band_pct(sm.average_close, sm.average_open)
        assert pct == pytest.approx(10.526, abs=0.01)

    def test_has_dead_band_false_without_measurement(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """has_dead_band is False when not measuring dead band.

        Technique: Specification-based — flag off by default.
        """
        sm.start(runs=1)
        _do_direction(sm, clock, offset=0.5, travel=8.0)
        _do_direction(sm, clock, offset=0.5, travel=9.0)

        assert sm.has_dead_band is False

    def test_average_dead_band_no_data_raises(
        self, sm: CalibrationStateMachine
    ) -> None:
        """Accessing average_dead_band without data raises CalibrationError.

        Technique: Error Guessing — accessing empty measurement list.
        """
        with pytest.raises(CalibrationError, match="no dead band measurements"):
            _ = sm.average_dead_band

    def test_cancel_clears_dead_band_data(self, clock: FakeClock) -> None:
        """Cancel clears dead band measurements.

        Technique: State Transition Testing — cancel resets all data.
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=1, measure_dead_band=True)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset
        clock.advance(1.0)
        sm.mark()  # dead band
        sm.cancel()

        assert sm.has_dead_band is False
        with pytest.raises(CalibrationError, match="no dead band measurements"):
            _ = sm.average_dead_band

    def test_without_dead_band_skips_timing_dead_band_state(
        self, sm: CalibrationStateMachine, clock: FakeClock
    ) -> None:
        """Without measure_dead_band, offset mark goes directly to TIMING.

        Technique: State Transition Testing — backward compatibility.
        """
        sm.start(runs=1)
        sm.go()
        clock.advance(0.5)
        sm.mark()  # offset mark

        assert sm.state is CalibrationState.TIMING

    def test_multi_run_dead_band_averages(self, clock: FakeClock) -> None:
        """Multi-run calibration averages dead band durations correctly.

        Technique: Specification-based — averaged dead band over 2 runs.
        """
        sm = CalibrationStateMachine(time_source=clock)
        sm.start(runs=2, measure_dead_band=True)

        # Run 1
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=0.8, travel=10.0)
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=0.8, travel=10.0)

        # Run 2
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.2, travel=10.0)
        _do_direction_with_dead_band(sm, clock, offset=0.5, dead_band=1.2, travel=10.0)

        assert sm.state is CalibrationState.COMPLETE
        assert sm.average_dead_band == pytest.approx(1.0)
