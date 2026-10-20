"""Unit tests for geiger2mqtt.domain.radiation — count and dose-rate maths.

Test Techniques Used:
- Boundary Value Analysis: window edges (exclusive start, inclusive end),
  readiness at exactly 60 s, no-pulse timeout at exactly the limit.
- Equivalence Partitioning: average window filled vs still filling; timeout
  enabled vs disabled (0); with and without a previous pulse.
- Specification-based: dose rate = cpm * factor; average from the true
  windowed count, scaled by elapsed time before the window fills.
- Error Guessing: a reading requested before readiness is rejected.
"""

from __future__ import annotations

import pytest

from geiger2mqtt.domain.radiation import (
    CPM_WINDOW,
    RadiationReading,
    compute_reading,
    count_in_window,
    is_ready,
    no_pulse_for,
)

pytestmark = pytest.mark.unit

FACTOR = 0.0057


class TestCountInWindow:
    def test_window_start_is_exclusive_and_end_inclusive(self) -> None:
        timestamps = [40.0, 40.001, 70.0, 100.0, 100.001]

        assert count_in_window(timestamps, now=100.0, window=60.0) == 3

    def test_empty(self) -> None:
        assert count_in_window([], now=100.0, window=60.0) == 0


class TestIsReady:
    @pytest.mark.parametrize(
        ("elapsed", "ready"), [(0.0, False), (59.999, False), (60.0, True)]
    )
    def test_ready_once_cpm_window_is_full(self, elapsed: float, ready: bool) -> None:
        assert is_ready(start=1000.0, now=1000.0 + elapsed) is ready


class TestComputeReading:
    def test_rejects_reading_before_ready(self) -> None:
        with pytest.raises(ValueError, match="CPM window"):
            compute_reading(
                [], start=0.0, now=59.0, average_window=900, conversion_factor=FACTOR
            )

    def test_full_average_window(self) -> None:
        """20 pulses in the last minute, 300 in the last 15 minutes."""
        start, now = 0.0, 2000.0
        last_minute = [now - 59 + i * 2.9 for i in range(20)]
        older = [now - 899 + i * 2.8 for i in range(280)]
        before_window = [now - 950.0] * 50

        reading = compute_reading(
            before_window + older + last_minute,
            start=start,
            now=now,
            average_window=900,
            conversion_factor=FACTOR,
        )

        assert reading == RadiationReading(
            cpm=20,
            dose_rate=round(20 * FACTOR, 4),
            dose_rate_avg=round(300 / 15 * FACTOR, 4),
        )

    def test_average_scales_by_elapsed_time_before_window_fills(self) -> None:
        """At 120 s, 40 pulses mean 20 CPM — not 40 / 15 minutes."""
        start = 500.0
        pulses = [start + 3.0 * i for i in range(1, 41)]

        reading = compute_reading(
            pulses,
            start=start,
            now=start + 120.0,
            average_window=900,
            conversion_factor=FACTOR,
        )

        assert reading.cpm == 20
        assert reading.dose_rate_avg == round(20 * FACTOR, 4)

    def test_first_reading_at_exactly_cpm_window(self) -> None:
        start = 0.0
        pulses = [float(i) for i in range(1, 31)]

        reading = compute_reading(
            pulses,
            start=start,
            now=CPM_WINDOW,
            average_window=900,
            conversion_factor=FACTOR,
        )

        assert reading.cpm == 30
        assert reading.dose_rate == reading.dose_rate_avg == round(30 * FACTOR, 4)

    def test_no_pulses_gives_zero(self) -> None:
        reading = compute_reading(
            [], start=0.0, now=600.0, average_window=900, conversion_factor=FACTOR
        )

        assert reading == RadiationReading(cpm=0, dose_rate=0.0, dose_rate_avg=0.0)

    def test_accepts_a_generator(self) -> None:
        reading = compute_reading(
            (t for t in [90.0, 100.0]),
            start=0.0,
            now=100.0,
            average_window=60,
            conversion_factor=1.0,
        )

        assert reading.cpm == 2
        assert reading.dose_rate_avg == 2.0


class TestNoPulseFor:
    def test_disabled_with_zero_timeout(self) -> None:
        assert no_pulse_for(None, start=0.0, now=1e9, timeout=0) is False

    @pytest.mark.parametrize(
        ("now", "expected"), [(399.999, False), (400.0, True), (500.0, True)]
    )
    def test_measured_from_last_pulse(self, now: float, expected: bool) -> None:
        assert no_pulse_for(100.0, start=0.0, now=now, timeout=300) is expected

    @pytest.mark.parametrize(("now", "expected"), [(299.999, False), (300.0, True)])
    def test_measured_from_start_without_any_pulse(
        self, now: float, expected: bool
    ) -> None:
        assert no_pulse_for(None, start=0.0, now=now, timeout=300) is expected
