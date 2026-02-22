"""Unit tests for gas2mqtt/domain/ewma.py — EWMA smoothing filter.

Test Techniques Used:
- Specification-based: EWMA formula verification with concrete values
- Boundary Value Analysis: alpha=1.0 edge case (no smoothing)
"""

from __future__ import annotations

import pytest

from gas2mqtt.domain.ewma import EwmaFilter


@pytest.mark.unit
class TestEwmaFilter:
    """Verify EWMA filter seeding, formula, and reset behaviour."""

    def test_initial_value_is_none(self) -> None:
        """Filter has no value before the first update."""
        f = EwmaFilter(alpha=0.2)
        assert f.value is None

    def test_first_update_returns_raw_value(self) -> None:
        """First update seeds the filter — returns the raw value unchanged."""
        f = EwmaFilter(alpha=0.2)

        result = f.update(100.0)

        assert result == 100.0
        assert f.value == 100.0

    def test_second_update_applies_smoothing(self) -> None:
        """Second update applies the EWMA formula.

        alpha=0.2, seed=100.0, raw=200.0
        expected = 0.8 * 100 + 0.2 * 200 = 80 + 40 = 120.0

        Technique: Specification-based — verifying the EWMA formula.
        """
        f = EwmaFilter(alpha=0.2)
        f.update(100.0)

        result = f.update(200.0)

        assert result == pytest.approx(120.0)
        assert f.value == pytest.approx(120.0)

    def test_alpha_one_means_no_smoothing(self) -> None:
        """alpha=1.0 tracks exactly — filtered value equals raw value.

        Technique: Boundary Value Analysis — alpha at upper bound.
        """
        f = EwmaFilter(alpha=1.0)
        f.update(50.0)

        result = f.update(200.0)

        assert result == pytest.approx(200.0)

    def test_heavy_smoothing(self) -> None:
        """alpha=0.01 barely moves the filtered value toward the new input.

        seed=100.0, raw=200.0
        expected = 0.99 * 100 + 0.01 * 200 = 99 + 2 = 101.0
        """
        f = EwmaFilter(alpha=0.01)
        f.update(100.0)

        result = f.update(200.0)

        assert result == pytest.approx(101.0)

    def test_convergence(self) -> None:
        """Feeding the same value repeatedly converges the filter to that value."""
        f = EwmaFilter(alpha=0.2)
        f.update(0.0)  # seed at 0

        for _ in range(200):
            f.update(100.0)

        assert f.value == pytest.approx(100.0, abs=0.01)

    def test_reset_clears_state(self) -> None:
        """Reset returns value to None."""
        f = EwmaFilter(alpha=0.2)
        f.update(42.0)

        f.reset()

        assert f.value is None

    def test_update_after_reset_uses_raw_value(self) -> None:
        """First update after reset re-seeds (no smoothing)."""
        f = EwmaFilter(alpha=0.2)
        f.update(100.0)
        f.update(200.0)  # now at 120.0
        f.reset()

        result = f.update(50.0)

        assert result == 50.0
        assert f.value == 50.0
