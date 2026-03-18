"""Magnetometer debug telemetry — raw 3-axis magnetic field readings.

Publishes raw Bx, By, Bz values from the QMC5883L sensor at the gas
counter's poll interval.  Disabled by default — enable via the
``enable_debug_device`` setting for calibration and troubleshooting.

MQTT state payload:
    {"bx": -1234, "by": 567, "bz": -4567}
"""

from __future__ import annotations

from gas2mqtt.ports import MagnetometerPort


async def magnetometer(
    magnetometer: MagnetometerPort,
) -> dict[str, object]:
    """Read and return raw magnetic field values.

    Args:
        magnetometer: Sensor adapter (injected by cosalette DI).

    Returns:
        ``{"bx": int, "by": int, "bz": int}`` — published to MQTT
        on every poll cycle.
    """
    reading = magnetometer.read()
    return {"bx": reading.bx, "by": reading.by, "bz": reading.bz}
