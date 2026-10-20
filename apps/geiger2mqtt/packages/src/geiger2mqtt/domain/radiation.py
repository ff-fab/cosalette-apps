"""Count-rate and dose-rate calculations over monotonic pulse timestamps.

All times are monotonic seconds supplied by the caller. A pulse at ``t`` lies
in the window of length ``w`` ending at ``now`` when ``now - w < t <= now``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CPM_WINDOW = 60.0
"""Seconds counted for CPM; also the wait before the first reading."""

DOSE_DECIMALS = 4
"""Decimal places kept for dose rates (0.1 nSv/h resolution)."""


@dataclass(frozen=True, slots=True)
class RadiationReading:
    """One published reading."""

    cpm: int
    dose_rate: float
    dose_rate_avg: float


def count_in_window(timestamps: Iterable[float], now: float, window: float) -> int:
    """Return the number of timestamps in the window ``(now - window, now]``."""
    return sum(1 for t in timestamps if now - window < t <= now)


def is_ready(start: float, now: float) -> bool:
    """Return whether the CPM window has been counted in full since ``start``."""
    return now - start >= CPM_WINDOW


def compute_reading(
    timestamps: Iterable[float],
    *,
    start: float,
    now: float,
    average_window: float,
    conversion_factor: float,
) -> RadiationReading:
    """Compute CPM and both dose rates.

    The average uses the true pulse count of the average window. Until that
    window has filled, it divides by the time elapsed since ``start`` instead
    of the full window, so the first readings are not biased low.

    Raises:
        ValueError: if called before :func:`is_ready`.
    """
    if not is_ready(start, now):
        raise ValueError("no reading before the CPM window has filled")
    pulses = list(timestamps)
    cpm = count_in_window(pulses, now, CPM_WINDOW)
    effective_window = min(average_window, now - start)
    avg_cpm = count_in_window(pulses, now, average_window) / (effective_window / 60)
    return RadiationReading(
        cpm=cpm,
        dose_rate=round(cpm * conversion_factor, DOSE_DECIMALS),
        dose_rate_avg=round(avg_cpm * conversion_factor, DOSE_DECIMALS),
    )


def no_pulse_for(
    last_pulse: float | None, *, start: float, now: float, timeout: float
) -> bool:
    """Return whether no pulse arrived for ``timeout`` seconds.

    Measured from the last pulse, or from ``start`` if none arrived yet. A
    ``timeout`` of 0 disables the check.
    """
    if timeout <= 0:
        return False
    since = start if last_pulse is None else last_pulse
    return now - since >= timeout
