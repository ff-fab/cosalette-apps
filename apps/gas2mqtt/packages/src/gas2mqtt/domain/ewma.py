"""Exponentially Weighted Moving Average (EWMA) filter.

Smooths noisy temperature readings by weighting recent values more
heavily. The alpha parameter controls smoothing strength:
    alpha = 1.0 → no smoothing (use raw value)
    alpha → 0.0 → heavy smoothing (slow response)

Formula: filtered = alpha * new_value + (1 - alpha) * previous_filtered

The first value initializes the filter (no smoothing applied).
"""

from __future__ import annotations


class EwmaFilter:
    """EWMA filter with configurable smoothing factor.

    Args:
        alpha: Smoothing factor in (0, 1]. Higher values track faster.
    """

    def __init__(self, alpha: float) -> None:
        self._alpha = alpha
        self._value: float | None = None

    @property
    def value(self) -> float | None:
        """Current filtered value, or ``None`` before the first update."""
        return self._value

    def update(self, raw: float) -> float:
        """Feed a raw measurement and return the smoothed value.

        The first call seeds the filter (returns *raw* unchanged).
        Subsequent calls apply the EWMA formula.
        """
        if self._value is None:
            self._value = raw
        else:
            self._value = (1 - self._alpha) * self._value + self._alpha * raw
        return self._value

    def reset(self) -> None:
        """Clear internal state so the next update re-seeds the filter."""
        self._value = None
