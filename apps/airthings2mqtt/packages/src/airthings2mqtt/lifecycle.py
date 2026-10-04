"""Radon measurement lifecycle across a sensor reset (ADR-004).

An Airthings Wave that loses power (a battery change) forgets its radon
averages and reports ``0`` for both until it has computed new ones. This module
tells those placeholders apart from measurements, using only the previous
reading kept in the per-device store. Pure functions: no I/O, no cosalette.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Any, cast

from airthings2mqtt.ports import AirthingsReading, MeasurementState

RESET_MIN_LTA = 20
"""Smallest previous long-term average (Bq/m³) whose collapse counts as a reset."""

RESET_DROP_RATIO = 0.25
"""A long-term average below this share of the previous one means a reset.

A long-term average moves slowly; a fall of more than 75 % between two polls
means the sensor started over.
"""


@dataclass(frozen=True, slots=True)
class ResetState:
    """What the app remembers about the sensor between polls and restarts.

    Attributes:
        last_lta: Last decoded long-term average (``0`` while warming up).
        reset_at: When the app last detected a sensor reset.
        lta_before_reset: Long-term average the last reset wiped.
        reset_count: Resets detected since the store was created.
    """

    last_lta: int | None = None
    reset_at: datetime | None = None
    lta_before_reset: int | None = None
    reset_count: int = 0

    @classmethod
    def from_dict(cls, data: object) -> ResetState:
        """Rebuild from :meth:`to_dict` output; anything else is a fresh state."""
        if not isinstance(data, dict):
            return cls()
        fields = cast("dict[str, Any]", data)
        keys = ("last_lta", "lta_before_reset", "reset_count")
        state = cls(**{k: fields[k] for k in keys if k in fields})
        if reset_at := fields.get("reset_at"):
            state = replace(state, reset_at=datetime.fromisoformat(reset_at))
        return state

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable form for the device store."""
        data = asdict(self)
        data["reset_at"] = self.reset_at.isoformat() if self.reset_at else None
        return data


def track(
    reading: AirthingsReading, state: ResetState, settle: timedelta
) -> tuple[AirthingsReading, ResetState, bool]:
    """Classify *reading* against *state*.

    Args:
        reading: The decoded reading; ``last_read`` is taken as "now".
        state: The state after the previous reading.
        settle: How long the long-term average stays provisional after a reset.

    Returns:
        The reading to publish (placeholders withheld, lifecycle fields set),
        the new state, and whether this reading revealed a reset.
    """
    lta = reading.radon_long_term_avg
    placeholder = reading.radon_24h_avg == 0 and lta == 0
    collapsed = (
        lta is not None
        and state.last_lta is not None
        and state.last_lta >= RESET_MIN_LTA
        and lta < state.last_lta * RESET_DROP_RATIO
    )
    # A 0/0 read after anything but another 0/0 read is a fresh reset.
    reset = (placeholder and state.last_lta != 0) or collapsed
    if reset:
        state = replace(
            state,
            reset_at=reading.last_read,
            lta_before_reset=state.last_lta,
            reset_count=state.reset_count + 1,
        )
    if lta is not None:
        state = replace(state, last_lta=lta)

    phase: MeasurementState
    if placeholder:
        phase = "warming_up"
        reading = replace(reading, radon_24h_avg=None, radon_long_term_avg=None)
    elif state.reset_at is not None and reading.last_read - state.reset_at < settle:
        phase = "provisional"
    else:
        phase = "ok"
    reading = replace(reading, measurement_state=phase, sensor_reset_at=state.reset_at)
    return reading, state, reset
