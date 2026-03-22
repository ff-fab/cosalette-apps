"""Unit tests for PositionTracker.

Test Techniques Used:
- State Transition Testing: STOPPED → OPENING → CLOSING state machine
- Boundary Value Analysis: Position clamping at 0% and 100%
- Specification-based Testing: Travel time offset, asymmetric durations
"""

from velux2mqtt.domain.position import MovementState, PositionTracker


def _make_tracker(
    *,
    duration_up: float = 20.0,
    duration_down: float = 20.0,
    offset: float = 1.0,
) -> tuple[PositionTracker, list[float]]:
    """Create a tracker with a controllable fake clock.

    Returns the tracker and a mutable list whose first element is
    the current time. Mutate clock[0] to advance time.
    """
    clock = [0.0]
    tracker = PositionTracker(
        travel_duration_up=duration_up,
        travel_duration_down=duration_down,
        travel_time_offset=offset,
        time_source=lambda: clock[0],
    )
    return tracker, clock


class TestBasicMovement:
    """Test simple open/close/stop sequences."""

    def test_initial_state(self) -> None:
        tracker, _ = _make_tracker()
        assert tracker.position == 0.0
        assert tracker.state == MovementState.STOPPED

    def test_full_open(self) -> None:
        """Opening for full duration reaches 100%."""
        tracker, clock = _make_tracker(duration_up=20.0, offset=0.0)

        tracker.start_opening()
        clock[0] = 20.0
        tracker.stop()

        assert tracker.position_int == 100
        assert tracker.state == MovementState.STOPPED

    def test_full_close_from_open(self) -> None:
        """Closing for full duration reaches 0%."""
        tracker, clock = _make_tracker(duration_down=20.0, offset=0.0)
        tracker.position = 100.0

        tracker.start_closing()
        clock[0] = 20.0
        tracker.stop()

        assert tracker.position_int == 0

    def test_partial_open(self) -> None:
        """Opening for half duration reaches ~50%."""
        tracker, clock = _make_tracker(duration_up=20.0, offset=0.0)

        tracker.start_opening()
        clock[0] = 10.0
        tracker.stop()

        assert tracker.position_int == 50

    def test_offset_subtracted(self) -> None:
        """Travel time offset reduces effective movement."""
        tracker, clock = _make_tracker(duration_up=20.0, offset=1.0)

        tracker.start_opening()
        clock[0] = 11.0  # 11s elapsed - 1s offset = 10s effective = 50%
        tracker.stop()

        assert tracker.position_int == 50

    def test_position_clamped_at_100(self) -> None:
        """Position cannot exceed 100% even with excess travel time."""
        tracker, clock = _make_tracker(duration_up=20.0, offset=0.0)

        tracker.start_opening()
        clock[0] = 30.0  # 150% worth of travel
        tracker.stop()

        assert tracker.position_int == 100

    def test_position_clamped_at_0(self) -> None:
        """Position cannot go below 0%."""
        tracker, clock = _make_tracker(duration_down=20.0, offset=0.0)
        tracker.position = 10.0

        tracker.start_closing()
        clock[0] = 30.0
        tracker.stop()

        assert tracker.position_int == 0


class TestIdempotent:
    """Test that repeated same-direction calls are no-ops."""

    def test_start_opening_while_opening(self) -> None:
        """Calling start_opening() while already opening preserves position."""
        tracker, clock = _make_tracker(duration_up=20.0, offset=0.0)

        tracker.start_opening()
        clock[0] = 10.0  # 50% traveled
        tracker.start_opening()  # should be no-op
        clock[0] = 20.0  # another 10s → should reach 100%
        tracker.stop()

        assert tracker.position_int == 100

    def test_start_closing_while_closing(self) -> None:
        """Calling start_closing() while already closing preserves position."""
        tracker, clock = _make_tracker(duration_down=20.0, offset=0.0)
        tracker.position = 100.0

        tracker.start_closing()
        clock[0] = 10.0  # 50% traveled
        tracker.start_closing()  # should be no-op
        clock[0] = 20.0  # another 10s → should reach 0%
        tracker.stop()

        assert tracker.position_int == 0


class TestDirectionChange:
    """Test changing direction mid-movement."""

    def test_open_then_close(self) -> None:
        """Switching from opening to closing updates position first."""
        tracker, clock = _make_tracker(duration_up=20.0, duration_down=20.0, offset=0.0)

        tracker.start_opening()
        clock[0] = 10.0  # 50%
        tracker.start_closing()  # should stop opening, apply elapsed
        assert tracker.position_int == 50

        clock[0] = 15.0  # 5s closing = 25% down
        tracker.stop()
        assert tracker.position_int == 25

    def test_close_then_open(self) -> None:
        """Switching from closing to opening updates position first."""
        tracker, clock = _make_tracker(duration_up=20.0, duration_down=20.0, offset=0.0)
        tracker.position = 80.0

        tracker.start_closing()
        clock[0] = 4.0  # 20% down → 60%
        tracker.start_opening()
        assert tracker.position_int == 60

        clock[0] = 12.0  # 8s opening = 40% up → 100%
        tracker.stop()
        assert tracker.position_int == 100


class TestFinalize:
    """Test endpoint finalization."""

    def test_finalize_open(self) -> None:
        tracker, _ = _make_tracker()
        tracker.position = 42.0
        tracker.finalize_open()
        assert tracker.position == 100.0
        assert tracker.state == MovementState.STOPPED

    def test_finalize_closed(self) -> None:
        tracker, _ = _make_tracker()
        tracker.position = 42.0
        tracker.finalize_closed()
        assert tracker.position == 0.0
        assert tracker.state == MovementState.STOPPED


class TestTravelTime:
    """Test travel time calculations."""

    def test_travel_time_open(self) -> None:
        tracker, _ = _make_tracker(duration_up=20.0, offset=1.0)
        # 0% → 50% = 50% of 20s + 1s offset = 11s
        assert tracker.travel_time_for(0.0, 50) == 11.0

    def test_travel_time_close(self) -> None:
        tracker, _ = _make_tracker(duration_down=18.0, offset=1.0)
        # 100% → 0% = 100% of 18s + 1s offset = 19s
        assert tracker.travel_time_for(100.0, 0) == 19.0

    def test_travel_time_asymmetric(self) -> None:
        """Different up/down durations produce different travel times."""
        tracker, _ = _make_tracker(duration_up=20.0, duration_down=18.0, offset=0.0)
        up_time = tracker.travel_time_for(0.0, 100)
        down_time = tracker.travel_time_for(100.0, 0)
        assert up_time == 20.0
        assert down_time == 18.0


class TestStopIdempotent:
    """Test that stopping while stopped is safe."""

    def test_stop_when_stopped(self) -> None:
        tracker, _ = _make_tracker()
        tracker.stop()  # should not raise
        assert tracker.position_int == 0
