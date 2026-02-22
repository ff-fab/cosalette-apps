"""Device handlers for gas2mqtt.

Contains cosalette device implementations:
- gas_counter: @app.device — stateful trigger detection + counter
- temperature: @app.telemetry — periodic temperature reporting
- magnetometer: @app.telemetry — debug raw magnetometer output (optional)
"""

from __future__ import annotations

from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import magnetometer_device, make_magnetometer_handler
from gas2mqtt.devices.temperature import make_temperature_handler, temperature_device

__all__ = [
    "gas_counter",
    "magnetometer_device",
    "make_magnetometer_handler",
    "make_temperature_handler",
    "temperature_device",
]
