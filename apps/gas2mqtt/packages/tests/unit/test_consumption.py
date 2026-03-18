"""Unit tests for gas2mqtt/domain/consumption.py — Gas consumption tracker.

Test Techniques Used:
- Specification-based: Liters-to-m³ conversion formula verification
- State Transition Testing: set → tick → reset lifecycle
"""

from __future__ import annotations

import pytest

from gas2mqtt.domain.consumption import ConsumptionTracker


@pytest.mark.unit
class TestConsumptionTracker:
    """Verify consumption tracking, ticking, setting, and resetting."""

    def test_initial_consumption_is_zero(self) -> None:
        """Default consumption starts at 0.0 m³."""
        tracker = ConsumptionTracker(liters_per_tick=10.0)
        assert tracker.consumption_m3 == 0.0

    def test_initial_consumption_with_start_value(self) -> None:
        """Consumption can be initialised to a non-zero value."""
        tracker = ConsumptionTracker(liters_per_tick=10.0, initial_m3=123.456)
        assert tracker.consumption_m3 == pytest.approx(123.456)

    def test_tick_increments_by_liters_per_tick(self) -> None:
        """One tick of 10 L adds 0.01 m³.

        Technique: Specification-based — 10 L / 1000 = 0.01 m³.
        """
        tracker = ConsumptionTracker(liters_per_tick=10.0)

        tracker.tick()

        assert tracker.consumption_m3 == pytest.approx(0.01)

    def test_multiple_ticks(self) -> None:
        """Five ticks of 10 L adds 0.05 m³."""
        tracker = ConsumptionTracker(liters_per_tick=10.0)

        for _ in range(5):
            tracker.tick()

        assert tracker.consumption_m3 == pytest.approx(0.05)

    def test_set_consumption_to_absolute_value(self) -> None:
        """set_consumption sets an explicit m³ value."""
        tracker = ConsumptionTracker(liters_per_tick=10.0)

        tracker.set_consumption(42.5)

        assert tracker.consumption_m3 == pytest.approx(42.5)

    def test_set_consumption_overwrites_ticks(self) -> None:
        """set_consumption replaces whatever was accumulated via ticks.

        Technique: State Transition — tick then set overwrites.
        """
        tracker = ConsumptionTracker(liters_per_tick=10.0)
        tracker.tick()
        tracker.tick()

        tracker.set_consumption(100.0)

        assert tracker.consumption_m3 == pytest.approx(100.0)

    def test_reset_to_zero(self) -> None:
        """Reset returns consumption to 0.0 m³."""
        tracker = ConsumptionTracker(liters_per_tick=10.0)
        tracker.tick()
        tracker.tick()

        tracker.reset()

        assert tracker.consumption_m3 == 0.0

    def test_tick_after_set_consumption(self) -> None:
        """Ticks continue from the set value.

        Technique: State Transition — set then tick accumulates.
        """
        tracker = ConsumptionTracker(liters_per_tick=10.0)
        tracker.set_consumption(100.0)

        tracker.tick()

        assert tracker.consumption_m3 == pytest.approx(100.01)

    def test_tick_returns_new_consumption(self) -> None:
        """tick() returns the updated consumption value."""
        tracker = ConsumptionTracker(liters_per_tick=10.0)

        result = tracker.tick()

        assert result == pytest.approx(0.01)
