"""airthings2mqtt application entry point.

Wires the cosalette App with the Airthings BLE telemetry device,
adapter, and settings.  The ``main()`` function is the CLI entry point.
"""

from __future__ import annotations

import cosalette

from airthings2mqtt.adapters.bleak import BleakAirthingsReader
from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.ports import AirthingsReaderPort
from airthings2mqtt.settings import Airthings2MqttSettings

app = cosalette.App(
    name="airthings2mqtt",
    settings_class=Airthings2MqttSettings,
    adapters={
        AirthingsReaderPort: (BleakAirthingsReader, FakeAirthingsReader),
    },
)


def _poll_interval(s: cosalette.Settings) -> float:
    """Deferred interval — resolved after settings are parsed."""
    if not isinstance(s, Airthings2MqttSettings):
        raise TypeError(
            f"_poll_interval expected Airthings2MqttSettings, got {type(s).__name__}"
        )
    return float(s.poll_interval)


@app.telemetry("airthings", interval=_poll_interval)
async def _telemetry(
    reader: AirthingsReaderPort,
    settings: Airthings2MqttSettings,
) -> dict[str, object]:
    """Read all sensor values and return state dict."""
    reading = await reader.read(settings.device_mac)
    return {
        "temperature": reading.temperature,
        "humidity": reading.humidity,
        "radon_24h_avg": reading.radon_24h_avg,
        "radon_long_term_avg": reading.radon_long_term_avg,
    }


def main() -> None:
    """Start the application."""
    app.run()
