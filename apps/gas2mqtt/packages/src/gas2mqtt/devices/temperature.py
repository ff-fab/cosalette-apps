"""Temperature telemetry device — periodic temperature reporting.

Reads raw temperature from the QMC5883L magnetometer, applies
empirical calibration (temp_scale * raw + temp_offset), and smooths
with an EWMA filter.

The handler is created via ``make_temperature_handler()``, which
captures the magnetometer adapter and settings in a closure.  The
:class:`EwmaFilter` state persists across calls because it lives
inside the closure.

MQTT state payload::

    {"temperature": 21.5}
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import cosalette

from gas2mqtt.domain.ewma import EwmaFilter
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

logger = logging.getLogger(__name__)


def make_temperature_handler(
    magnetometer: MagnetometerPort,
    settings: Gas2MqttSettings,
) -> Callable[[], Awaitable[dict[str, object]]]:
    """Create a temperature telemetry handler with captured state.

    The returned async function reads temperature from the magnetometer,
    applies linear calibration (``temp_scale * raw + temp_offset``), and
    EWMA-filters the result.  The :class:`EwmaFilter` is created once
    and its state persists across invocations via closure capture.

    Args:
        magnetometer: Adapter for reading raw temperature.
        settings: Application settings with calibration coefficients.

    Returns:
        Zero-parameter async function suitable for
        ``@app.telemetry`` registration.
    """
    ewma = EwmaFilter(settings.ewma_alpha)

    async def handler() -> dict[str, object]:
        reading = magnetometer.read()
        raw_celsius = (
            settings.temp_scale * reading.temperature_raw + settings.temp_offset
        )
        filtered = ewma.update(raw_celsius)
        return {"temperature": round(filtered, 1)}

    return handler


async def temperature_device(ctx: cosalette.DeviceContext) -> None:
    """Temperature device coroutine — polls and publishes filtered temperature.

    Designed for ``@app.device("temperature")`` registration.  Creates a
    temperature handler with the EWMA filter, publishes an initial state,
    then loops at ``settings.temperature_interval``.

    Args:
        ctx: Per-device context provided by cosalette.
    """
    settings: Gas2MqttSettings = ctx.settings  # type: ignore[assignment]
    magnetometer = ctx.adapter(MagnetometerPort)  # type: ignore[type-abstract]
    handler = make_temperature_handler(magnetometer, settings)
    await ctx.publish_state(await handler())
    while not ctx.shutdown_requested:
        await ctx.sleep(settings.temperature_interval)
        await ctx.publish_state(await handler())
