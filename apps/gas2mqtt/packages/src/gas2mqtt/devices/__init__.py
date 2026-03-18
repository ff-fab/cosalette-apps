"""Device handlers for gas2mqtt.

Contains cosalette device implementations:
- gas_counter: @app.device — stateful trigger detection + counter
- temperature: @app.telemetry — PT1-smoothed temperature from magnetometer
- magnetometer: @app.telemetry — raw magnetometer readings (debug only)
"""

from __future__ import annotations

from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import temperature

__all__ = [
    "gas_counter",
    "magnetometer",
    "temperature",
]
