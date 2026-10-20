"""Radiation telemetry: counts per minute and dose rates from the pulse counter.

MQTT state payload on ``geiger2mqtt/radiation/state``::

    {"cpm": 21, "dose_rate": 0.1197, "dose_rate_avg": 0.1083}
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from cosalette.schema import consumer
from pydantic import Field

from geiger2mqtt.domain.radiation import (
    CPM_WINDOW,
    compute_reading,
    is_ready,
    no_pulse_for,
)
from geiger2mqtt.ports import PulseCounterPort
from geiger2mqtt.settings import Geiger2MqttSettings

_ICON = "mdi:radioactive"


class NoPulseError(Exception):
    """No pulse arrived within ``NO_PULSE_TIMEOUT``: the tube or wiring is dead.

    Mapped via ``unavailable_on``, so the channel goes offline while the app
    keeps running and recovers on the next pulse.
    """


@dataclass(frozen=True, slots=True)
class RadiationState:
    """Published ``radiation`` payload; the ``state_model`` of the channel.

    No ``device_class``: Home Assistant has none for radiation.
    """

    cpm: Annotated[
        int,
        Field(
            json_schema_extra=consumer(
                display_name="Counts per minute",
                unit="CPM",
                state_class="measurement",
                icon=_ICON,
            )
        ),
    ]
    dose_rate: Annotated[
        float,
        Field(
            json_schema_extra=consumer(
                display_name="Dose rate",
                unit="µSv/h",
                state_class="measurement",
                icon=_ICON,
            )
        ),
    ]
    dose_rate_avg: Annotated[
        float,
        Field(
            json_schema_extra=consumer(
                display_name="Average dose rate",
                unit="µSv/h",
                state_class="measurement",
                icon=_ICON,
            )
        ),
    ]


async def radiation(
    counter: PulseCounterPort, settings: Geiger2MqttSettings
) -> RadiationState | None:
    """Return the current reading, or None until the CPM window has filled.

    Raises:
        NoPulseError: No pulse for ``no_pulse_timeout`` seconds (0 disables).
    """
    now = counter.now()
    start = counter.started_at
    if no_pulse_for(
        counter.last_pulse(),
        start=start,
        now=now,
        timeout=settings.no_pulse_timeout,
    ):
        msg = f"No pulse for {settings.no_pulse_timeout:g} s"
        raise NoPulseError(msg)
    if not is_ready(start, now):
        return None
    window = max(CPM_WINDOW, settings.average_window)
    reading = compute_reading(
        counter.snapshot(since=now - window),
        start=start,
        now=now,
        average_window=settings.average_window,
        conversion_factor=settings.conversion_factor,
    )
    return RadiationState(
        cpm=reading.cpm,
        dose_rate=reading.dose_rate,
        dose_rate_avg=reading.dose_rate_avg,
    )
