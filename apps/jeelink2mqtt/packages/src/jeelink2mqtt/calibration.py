"""Per-sensor calibration offset application.

Applies configurable temperature and humidity offsets to filtered
sensor readings, compensating for individual sensor inaccuracies.
"""

from __future__ import annotations

import math
from dataclasses import replace

from jeelink2mqtt.models import SensorConfig, SensorReading


def apply_calibration(reading: SensorReading, config: SensorConfig) -> SensorReading:
    """Return a new reading with calibration offsets applied.

    Temperature is offset directly; humidity uses ``math.floor(x + 0.5)``
    (standard half-up rounding, **not** Python's default banker's
    rounding) and is clamped to 0–100.

    Uses :func:`dataclasses.replace` so that any future fields added to
    :class:`SensorReading` are preserved automatically.
    """
    calibrated_temp = reading.temperature + config.temp_offset
    calibrated_humidity = int(
        max(
            0,
            min(100, reading.humidity + math.floor(config.humidity_offset + 0.5)),
        ),
    )

    return replace(
        reading,
        temperature=calibrated_temp,
        humidity=calibrated_humidity,
    )
