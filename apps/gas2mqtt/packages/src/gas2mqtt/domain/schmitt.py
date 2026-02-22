"""Schmitt trigger for gas meter rotation detection.

A Schmitt trigger is a comparator with hysteresis. It converts the
continuous Bz magnetic field value into a clean binary signal by
using two thresholds: level + hysteresis (upper) and level - hysteresis
(lower). This prevents rapid toggling when Bz is near the threshold.

State transitions:
    LOW → HIGH: when bz > level + hysteresis  (magnet present)
    HIGH → LOW: when bz < level - hysteresis  (magnet absent)
    Rising edge (LOW → HIGH): counts as one gas meter tick
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class TriggerState(enum.Enum):
    """Binary state of the Schmitt trigger."""

    LOW = "low"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class TriggerEvent:
    """Record of a state transition in the Schmitt trigger.

    Attributes:
        previous: State before the transition.
        current: State after the transition.
        is_rising_edge: True when transitioning LOW → HIGH (one gas tick).
    """

    previous: TriggerState
    current: TriggerState
    is_rising_edge: bool


class SchmittTrigger:
    """Schmitt trigger with configurable level and hysteresis.

    Args:
        level: Centre threshold for the Bz magnetic field value.
        hysteresis: Half-width of the dead band around *level*.
    """

    def __init__(self, level: int, hysteresis: int) -> None:
        self._level = level
        self._hysteresis = hysteresis
        self._state = TriggerState.LOW

    @property
    def state(self) -> TriggerState:
        """Current trigger state."""
        return self._state

    def update(self, bz: int) -> TriggerEvent | None:
        """Feed a Bz magnetometer value and return any state change.

        Returns:
            A ``TriggerEvent`` when the state transitions, otherwise ``None``.
        """
        upper = self._level + self._hysteresis
        lower = self._level - self._hysteresis

        if bz > upper:
            new_state = TriggerState.HIGH
        elif bz < lower:
            new_state = TriggerState.LOW
        else:
            # Inside hysteresis band — no change.
            return None

        if new_state == self._state:
            return None

        previous = self._state
        self._state = new_state
        is_rising = previous is TriggerState.LOW and new_state is TriggerState.HIGH
        return TriggerEvent(
            previous=previous,
            current=new_state,
            is_rising_edge=is_rising,
        )

    def reset(self) -> None:
        """Reset the trigger to the initial ``LOW`` state."""
        self._state = TriggerState.LOW
