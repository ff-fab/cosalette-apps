"""Airthings Wave BLE telemetry — periodic sensor readings.

Reads temperature, humidity, and radon levels from an Airthings Wave
sensor over BLE.  The framework's error isolation handles exceptions:
errors are logged, published to the error topic, and the poll loop
continues automatically.

MQTT state payload::

    {
        "temperature": 21.5,
        "humidity": 45.0,
        "radon_24h_avg": 80,
        "radon_long_term_avg": 65
    }
"""

from __future__ import annotations

from airthings2mqtt.ports import AirthingsReaderPort
from airthings2mqtt.settings import Airthings2MqttSettings


async def telemetry(
    reader: AirthingsReaderPort,
    settings: Airthings2MqttSettings,
) -> dict[str, object]:
    """Read all sensor values and return state dict.

    Args:
        reader: BLE sensor adapter (injected by cosalette DI).
        settings: Application settings with device MAC address.

    Returns:
        Dict with temperature, humidity, radon_24h_avg, and
        radon_long_term_avg — published to MQTT by the framework.

    Raises:
        BleConnectionError: If the device cannot be reached.
        BleReadError: If a GATT characteristic cannot be read.
        BleTimeoutError: If the connection or read times out.
    """
    reading = await reader.read(settings.device_mac)
    return {
        "temperature": reading.temperature,
        "humidity": reading.humidity,
        "radon_24h_avg": reading.radon_24h_avg,
        "radon_long_term_avg": reading.radon_long_term_avg,
    }
