"""Device handlers for airthings2mqtt.

Contains cosalette device implementations:
- telemetry: @app.telemetry — BLE sensor readings (temperature, humidity, radon)
"""

from __future__ import annotations

from airthings2mqtt.devices.telemetry import telemetry

__all__ = [
    "telemetry",
]
