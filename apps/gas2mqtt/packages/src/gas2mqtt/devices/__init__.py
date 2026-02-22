"""Device handlers for gas2mqtt.

Contains cosalette device implementations:
- gas_counter: @app.device — stateful trigger detection + counter
- temperature: handler factory for @app.telemetry registration in main
- magnetometer: handler factory for @app.telemetry registration in main
"""

from __future__ import annotations

from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import make_magnetometer_handler
from gas2mqtt.devices.temperature import make_temperature_handler

__all__ = [
    "gas_counter",
    "make_magnetometer_handler",
    "make_temperature_handler",
]
