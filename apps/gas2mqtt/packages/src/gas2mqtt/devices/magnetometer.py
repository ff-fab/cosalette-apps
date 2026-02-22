"""Debug magnetometer telemetry handler — pure handler factory.

Optional device that publishes raw magnetic field values (bx, by, bz)
for debugging and calibration.  Conditional registration (based on
``settings.enable_debug_device``) happens in :mod:`gas2mqtt.main`.

MQTT state payload::

    {"bx": 123, "by": -456, "bz": -5000}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from gas2mqtt.ports import MagnetometerPort


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
