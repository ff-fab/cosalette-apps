"""Production reading pipeline for jeelink2mqtt.

Exposes the named filter → calibrate stage used by the main receiver
loop in :mod:`jeelink2mqtt.main`.
"""

from __future__ import annotations

from dataclasses import replace

from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading


def filter_and_calibrate(
    reading: SensorReading,
    config: SensorConfig,
    filter_bank: FilterBank,
) -> SensorReading:
    """Filter → calibrate a raw reading, returning a calibrated SensorReading.

    Applies per-sensor median filtering (outlier rejection) followed by
    configurable calibration offsets.  This is the hot path for every
    mapped sensor reading in the main receiver loop.
    """
    temp, humidity = filter_bank.filter(reading)
    filtered = replace(reading, temperature=temp, humidity=int(humidity))
    return apply_calibration(filtered, config)
