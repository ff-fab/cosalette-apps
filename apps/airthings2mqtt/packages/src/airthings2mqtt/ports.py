"""Hardware adapter ports for airthings2mqtt.

Defines Protocol classes for hardware interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AirthingsReading:
    """A single reading from an Airthings Wave sensor.

    Attributes:
        temperature: Temperature in degrees Celsius.
        humidity: Relative humidity as a percentage.
        radon_24h_avg: 24-hour average radon level in Bq/m³.
        radon_long_term_avg: Long-term average radon level in Bq/m³.
    """

    temperature: float
    humidity: float
    radon_24h_avg: int
    radon_long_term_avg: int


@runtime_checkable
class AirthingsReaderPort(Protocol):
    """Port for reading Airthings Wave BLE sensor data.

    Implementations must connect to the BLE device, read the four
    GATT characteristics (temperature, humidity, radon 24h, radon
    long-term), and return an AirthingsReading.
    """

    async def read(self, mac: str) -> AirthingsReading:
        """Read sensor data from the Airthings Wave device.

        Connects to the device, reads all four characteristics,
        disconnects, and returns the parsed reading.

        Args:
            mac: Bluetooth MAC address of the Airthings Wave device.

        Returns:
            AirthingsReading with temperature, humidity, and radon values.

        Raises:
            BleConnectionError: If the device cannot be reached.
            BleReadError: If a GATT characteristic cannot be read.
            BleTimeoutError: If the connection or read times out.
        """
        ...
