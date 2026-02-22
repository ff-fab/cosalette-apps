"""Debug magnetometer telemetry device — raw sensor output.

Optional device that publishes raw magnetic field values (bx, by, bz)
for debugging and calibration.  Only registered when
``settings.enable_debug_device`` is ``True``.

MQTT state payload::

    {"bx": 123, "by": -456, "bz": -5000}
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

import cosalette

from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

logger = logging.getLogger(__name__)


def make_magnetometer_handler(
    magnetometer: MagnetometerPort,
) -> Callable[[], Awaitable[dict[str, object]]]:
    """Create a debug magnetometer telemetry handler.

    Returns raw *bx*, *by*, *bz* values from the magnetometer on each
    poll.  Useful for threshold calibration and sensor debugging.

    Args:
        magnetometer: Adapter for reading magnetic field values.

    Returns:
        Zero-parameter async function suitable for
        ``@app.telemetry`` registration.
    """

    async def handler() -> dict[str, object]:
        reading = magnetometer.read()
        return {"bx": reading.bx, "by": reading.by, "bz": reading.bz}

    return handler


async def magnetometer_device(ctx: cosalette.DeviceContext) -> None:
    """Debug magnetometer device coroutine — optional raw sensor output.

    Returns immediately when ``settings.enable_debug_device`` is *False*.
    Otherwise publishes raw bx/by/bz values at ``poll_interval``.

    Args:
        ctx: Per-device context provided by cosalette.
    """
    settings: Gas2MqttSettings = ctx.settings  # type: ignore[assignment]
    if not settings.enable_debug_device:
        return
    magnetometer = ctx.adapter(MagnetometerPort)  # type: ignore[type-abstract]
    handler = make_magnetometer_handler(magnetometer)
    await ctx.publish_state(await handler())
    while not ctx.shutdown_requested:
        await ctx.sleep(settings.poll_interval)
        await ctx.publish_state(await handler())
