"""Drift compensation — automatic endpoint recalibration.

After several consecutive intermediate moves (not to 0% or 100%),
position uncertainty accumulates. The DriftCompensator detects this
and plans recalibration moves through a known endpoint before
reaching the target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MoveStep:
    """A single step in a (possibly multi-step) movement plan.

    Attributes:
        target: Target position (0–100).
        is_recalibration: True if this step exists only to establish
            a known reference position.
    """

    target: int
    is_recalibration: bool = False


class DriftCompensator:
    """Tracks intermediate moves and plans endpoint recalibration.

    After ``threshold`` consecutive intermediate-to-intermediate moves,
    the next intermediate move will first travel to a known endpoint
    (0% or 100%) before proceeding to the target. The endpoint is
    chosen to minimize total travel distance.

    Args:
        threshold: Number of consecutive intermediate moves before
            recalibration is triggered. 0 disables drift compensation.
    """

    def __init__(self, threshold: int = 2) -> None:
        self._threshold = threshold
        self._consecutive_intermediate: int = 0

    @property
    def consecutive_intermediate(self) -> int:
        """Number of consecutive intermediate moves since last endpoint."""
        return self._consecutive_intermediate

    def reset(self) -> None:
        """Reset the intermediate move counter (called on endpoint arrival)."""
        self._consecutive_intermediate = 0

    def needs_recalibration(self, target: int) -> bool:
        """Check if a recalibration move is needed before reaching target.

        Returns True when:
        - Drift compensation is enabled (threshold > 0)
        - The target is intermediate (not 0 or 100)
        - The consecutive intermediate move count >= threshold
        """
        if self._threshold == 0:
            return False
        if target in (0, 100):
            return False
        return self._consecutive_intermediate >= self._threshold

    def plan_move(self, current_pos: float, target: int) -> list[MoveStep]:
        """Plan the movement sequence to reach the target position.

        If recalibration is needed, returns a two-step sequence:
        first move to the optimal endpoint, then to the target.
        Otherwise returns a single direct move.

        After planning, updates the internal counter:
        - Endpoint targets (0/100) reset the counter
        - Intermediate targets increment it

        Args:
            current_pos: Current estimated position (0–100).
            target: Desired target position (0–100).

        Returns:
            List of MoveStep(s) to execute in order.
        """
        if target in (0, 100):
            self.reset()
            return [MoveStep(target=target)]

        if not self.needs_recalibration(target):
            self._consecutive_intermediate += 1
            return [MoveStep(target=target)]

        # Recalibration needed: choose endpoint that minimizes total travel
        endpoint = self._optimal_endpoint(current_pos, target)
        self.reset()
        self._consecutive_intermediate = 1  # the final move to target counts
        return [
            MoveStep(target=endpoint, is_recalibration=True),
            MoveStep(target=target),
        ]

    @staticmethod
    def _optimal_endpoint(current_pos: float, target: int) -> int:
        """Choose the endpoint (0 or 100) that minimizes total travel.

        Total travel = |current → endpoint| + |endpoint → target|

        Args:
            current_pos: Current position.
            target: Final target position.

        Returns:
            0 or 100.
        """
        via_close = abs(current_pos - 0) + abs(0 - target)
        via_open = abs(current_pos - 100) + abs(100 - target)
        return 0 if via_close <= via_open else 100
