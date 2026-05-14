"""Production reading pipeline for jeelink2mqtt.

Exposes the named filter → calibrate stage used by the main receiver
loop in :mod:`jeelink2mqtt.main`.  Keeping the mechanics here lets
``main.py`` spell out the hot path by name without burying it inside
:class:`~jeelink2mqtt.state.SharedState`.
"""

from __future__ import annotations

from dataclasses import replace

from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.state import SharedState


def filter_and_calibrate(
    reading: SensorReading,
    config: SensorConfig,
    state: SharedState,
) -> SensorReading:
    """Filter → calibrate a raw reading, returning a calibrated SensorReading.

    Applies per-sensor median filtering (outlier rejection) followed by
    configurable calibration offsets.  This is the hot path for every
    mapped sensor reading in the main receiver loop.
    """
    temp, humidity = state.filter_bank.filter(reading)
    filtered = replace(reading, temperature=temp, humidity=int(humidity))
    return apply_calibration(filtered, config)
