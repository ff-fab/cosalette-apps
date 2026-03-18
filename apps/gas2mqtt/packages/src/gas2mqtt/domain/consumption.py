"""Gas consumption tracker.

Tracks cumulative gas consumption in cubic meters. Each gas meter tick
represents a configurable amount of gas (default: 10 liters = 0.01 m³).

The consumption value can be:
- Incremented by ticks (each tick adds liters_per_tick / 1000 m³)
- Set to an absolute value via MQTT command
- Reset to zero

This is an optional feature (enabled via settings).
"""

from __future__ import annotations


class ConsumptionTracker:
    """Cumulative gas consumption counter.

    Args:
        liters_per_tick: Liters of gas per meter tick.
        initial_m3: Starting consumption in cubic meters.
    """

    def __init__(self, liters_per_tick: float, initial_m3: float = 0.0) -> None:
        self._liters_per_tick = liters_per_tick
        self._consumption_m3 = initial_m3

    @property
    def consumption_m3(self) -> float:
        """Current cumulative consumption in cubic meters."""
        return self._consumption_m3

    def tick(self) -> float:
        """Record one gas meter tick and return the new consumption."""
        self._consumption_m3 += self._liters_per_tick / 1000.0
        return self._consumption_m3

    def set_consumption(self, m3: float) -> None:
        """Set the consumption to an absolute value (e.g. from MQTT)."""
        self._consumption_m3 = m3

    def reset(self) -> None:
        """Reset consumption to zero."""
        self._consumption_m3 = 0.0
