"""Temperature telemetry — PT1-filtered, calibrated sensor readings.

Reads the raw temperature from the magnetometer's built-in sensor,
applies a linear calibration (``temp_scale * raw + temp_offset``),
then smooths via an exponentially-weighted PT1 (first-order lag) filter.

The ``OnChange`` publish strategy ensures readings are only published
when the filtered value shifts by more than 0.05 °C, avoiding MQTT
chatter for sensor noise.

MQTT state payload:
    {"temperature": 22.5}
"""

from __future__ import annotations

from cosalette import Pt1Filter

from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings


def make_pt1(settings: Gas2MqttSettings) -> Pt1Filter:
    """Create PT1 filter from settings for temperature smoothing.

    This is the ``init=`` factory: cosalette calls it once before the
    handler loop and injects the returned ``Pt1Filter`` by type.
    """
    return Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)


async def temperature(
    magnetometer: MagnetometerPort,
    settings: Gas2MqttSettings,
    pt1: Pt1Filter,
) -> dict[str, object]:
    """Read temperature, calibrate, filter, and return state dict.

    Args:
        magnetometer: Sensor adapter (injected by cosalette DI).
        settings: Application settings with calibration coefficients.
        pt1: PT1 filter instance (created by :func:`make_pt1`).

    Returns:
        ``{"temperature": <rounded float>}`` — published to MQTT by
        the framework when the ``OnChange`` strategy fires.
    """
    reading = magnetometer.read()
    raw_celsius = settings.temp_scale * reading.temperature_raw + settings.temp_offset
    return {"temperature": round(pt1.update(raw_celsius), 1)}
