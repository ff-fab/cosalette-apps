"""Unit tests for gas2mqtt/domain/schmitt.py — Schmitt trigger state machine.

Test Techniques Used:
- State Transition Testing: LOW/HIGH transitions on threshold crossings
- Boundary Value Analysis: Exact threshold boundary values
- Error Guessing: Frozen TriggerEvent immutability
"""

from __future__ import annotations

import pytest

from gas2mqtt.domain.schmitt import SchmittTrigger, TriggerEvent, TriggerState

# Default thresholds: level=-5000, hysteresis=700
# Upper threshold: -5000 + 700 = -4300
# Lower threshold: -5000 - 700 = -5700

LEVEL = -5000
HYSTERESIS = 700
UPPER = LEVEL + HYSTERESIS  # -4300
LOWER = LEVEL - HYSTERESIS  # -5700


# ======================================================================
# TriggerState enum
# ======================================================================


@pytest.mark.unit
class TestTriggerState:
    """Verify TriggerState enum members."""

    def test_has_low_and_high_values(self) -> None:
        """Enum exposes LOW and HIGH members."""
        assert TriggerState.LOW is not TriggerState.HIGH
        assert TriggerState.LOW.value == "low"
        assert TriggerState.HIGH.value == "high"


# ======================================================================
# TriggerEvent dataclass
# ======================================================================


@pytest.mark.unit
class TestTriggerEvent:
    """Verify TriggerEvent construction and immutability."""

    def test_rising_edge_detection(self) -> None:
        """Rising edge (LOW → HIGH) sets is_rising_edge True."""
        event = TriggerEvent(
            previous=TriggerState.LOW,
            current=TriggerState.HIGH,
            is_rising_edge=True,
        )
        assert event.is_rising_edge is True

    def test_falling_edge_detection(self) -> None:
        """Falling edge (HIGH → LOW) sets is_rising_edge False."""
        event = TriggerEvent(
            previous=TriggerState.HIGH,
            current=TriggerState.LOW,
            is_rising_edge=False,
        )
        assert event.is_rising_edge is False

    def test_frozen_immutability(self) -> None:
        """TriggerEvent is frozen — mutation raises FrozenInstanceError.

        Technique: Error Guessing — anticipating specific failure mode.
        """
        event = TriggerEvent(
            previous=TriggerState.LOW,
            current=TriggerState.HIGH,
            is_rising_edge=True,
        )
        with pytest.raises(AttributeError):
            event.current = TriggerState.LOW  # type: ignore[misc]


# ======================================================================
# SchmittTrigger
# ======================================================================


@pytest.mark.unit
class TestSchmittTrigger:
    """Verify Schmitt trigger state transitions and hysteresis logic.

    Uses level=-5000, hysteresis=700:
    - Upper threshold = -4300  (transition LOW → HIGH when bz > -4300)
    - Lower threshold = -5700  (transition HIGH → LOW when bz < -5700)
    """

    # --- Initial state ---

    def test_initial_state_is_low(self) -> None:
        """Trigger starts in LOW state."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        assert trigger.state is TriggerState.LOW

    # --- Hysteresis band ---

    def test_no_event_when_in_hysteresis_band(self) -> None:
        """Values inside the dead band produce no event.

        Technique: State Transition Testing — staying in hysteresis band.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        # Feed a value right in the centre of the band.
        result = trigger.update(LEVEL)

        assert result is None
        assert trigger.state is TriggerState.LOW

    # --- State transitions ---

    def test_transition_low_to_high(self) -> None:
        """Bz crossing above upper threshold triggers LOW → HIGH.

        Technique: State Transition Testing.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        event = trigger.update(UPPER + 1)  # -4299

        assert event is not None
        assert event.previous is TriggerState.LOW
        assert event.current is TriggerState.HIGH
        assert trigger.state is TriggerState.HIGH

    def test_transition_high_to_low(self) -> None:
        """Bz crossing below lower threshold triggers HIGH → LOW.

        Technique: State Transition Testing.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # move to HIGH first

        event = trigger.update(LOWER - 1)  # -5701

        assert event is not None
        assert event.previous is TriggerState.HIGH
        assert event.current is TriggerState.LOW
        assert trigger.state is TriggerState.LOW

    # --- Rising edge flag ---

    def test_rising_edge_is_true_on_low_to_high(self) -> None:
        """LOW → HIGH transition is a rising edge (gas tick)."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        event = trigger.update(UPPER + 1)

        assert event is not None
        assert event.is_rising_edge is True

    def test_rising_edge_is_false_on_high_to_low(self) -> None:
        """HIGH → LOW transition is NOT a rising edge."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # move to HIGH

        event = trigger.update(LOWER - 1)

        assert event is not None
        assert event.is_rising_edge is False

    # --- Idempotent updates ---

    def test_no_event_on_repeated_high(self) -> None:
        """Multiple values above threshold after initial transition produce no event."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # first transition

        result = trigger.update(UPPER + 100)

        assert result is None
        assert trigger.state is TriggerState.HIGH

    def test_no_event_on_repeated_low(self) -> None:
        """Multiple values below threshold produce no event while already LOW."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        result = trigger.update(LOWER - 100)

        assert result is None
        assert trigger.state is TriggerState.LOW

    # --- Full cycle ---

    def test_full_cycle(self) -> None:
        """LOW → HIGH → LOW → HIGH produces exactly two rising edges.

        Technique: State Transition Testing — complete cycle verification.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        rising_edges: list[TriggerEvent] = []

        for bz in [UPPER + 1, LOWER - 1, UPPER + 1]:
            event = trigger.update(bz)
            if event is not None and event.is_rising_edge:
                rising_edges.append(event)

        assert len(rising_edges) == 2

    # --- Boundary value analysis ---

    def test_boundary_at_upper_threshold(self) -> None:
        """Bz exactly at upper threshold (-4300) does NOT trigger transition.

        Technique: Boundary Value Analysis — value on boundary.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        result = trigger.update(UPPER)  # -4300

        assert result is None
        assert trigger.state is TriggerState.LOW

    def test_boundary_above_upper_threshold(self) -> None:
        """Bz one above upper threshold (-4299) triggers LOW → HIGH.

        Technique: Boundary Value Analysis — value just past boundary.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        event = trigger.update(UPPER + 1)  # -4299

        assert event is not None
        assert event.current is TriggerState.HIGH

    def test_boundary_at_lower_threshold(self) -> None:
        """Bz exactly at lower threshold (-5700) does NOT trigger transition.

        Technique: Boundary Value Analysis — value on boundary.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # move to HIGH

        result = trigger.update(LOWER)  # -5700

        assert result is None
        assert trigger.state is TriggerState.HIGH

    def test_boundary_below_lower_threshold(self) -> None:
        """Bz one below lower threshold (-5701) triggers HIGH → LOW.

        Technique: Boundary Value Analysis — value just past boundary.
        """
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # move to HIGH

        event = trigger.update(LOWER - 1)  # -5701

        assert event is not None
        assert event.current is TriggerState.LOW

    # --- Reset ---

    def test_reset_returns_to_low(self) -> None:
        """Reset restores trigger to initial LOW state."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)

        trigger.reset()

        assert trigger.state is TriggerState.LOW

    def test_reset_from_high_state(self) -> None:
        """Reset from HIGH returns to LOW, allowing a fresh rising edge."""
        trigger = SchmittTrigger(level=LEVEL, hysteresis=HYSTERESIS)
        trigger.update(UPPER + 1)  # move to HIGH
        assert trigger.state is TriggerState.HIGH

        trigger.reset()

        assert trigger.state is TriggerState.LOW
        # Verify a new rising edge can occur.
        event = trigger.update(UPPER + 1)
        assert event is not None
        assert event.is_rising_edge is True
