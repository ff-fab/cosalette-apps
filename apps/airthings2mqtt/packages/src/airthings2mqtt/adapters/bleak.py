"""Bleak-based BLE adapter for Airthings Wave sensors.

Connects to an Airthings Wave device via BLE, reads the four GATT
characteristics (temperature, humidity, radon 24h, radon long-term),
and returns an AirthingsReading.
"""

from __future__ import annotations

import struct

from bleak import BleakClient

from airthings2mqtt.errors import ERROR_TYPE_MAP, BleReadError
from airthings2mqtt.ports import AirthingsReading

# BLE GATT characteristic UUIDs
_UUID_TEMPERATURE = "00002a6e-0000-1000-8000-00805f9b34fb"
_UUID_HUMIDITY = "00002a6f-0000-1000-8000-00805f9b34fb"
_UUID_RADON_24H = "b42e01aa-ade7-11e4-89d3-123b93f75cba"
_UUID_RADON_LTA = "b42e0a4c-ade7-11e4-89d3-123b93f75cba"


class BleakAirthingsReader:
    """Production adapter for reading Airthings Wave sensors via Bleak.

    Connects to the device, reads four GATT characteristics, disconnects,
    and returns the parsed AirthingsReading. Each read() call is a full
    connect-read-disconnect cycle.
    """

    async def read(self, mac: str) -> AirthingsReading:
        """Read sensor data from the Airthings Wave device.

        Args:
            mac: Bluetooth MAC address of the Airthings Wave device.

        Returns:
            AirthingsReading with parsed sensor values.

        Raises:
            BleConnectionError: If the device cannot be reached.
            BleReadError: If a GATT characteristic cannot be read.
            BleTimeoutError: If the connection or read times out.
        """
        try:
            async with BleakClient(mac) as client:
                raw_temp = await client.read_gatt_char(_UUID_TEMPERATURE)
                raw_hum = await client.read_gatt_char(_UUID_HUMIDITY)
                raw_radon_24h = await client.read_gatt_char(_UUID_RADON_24H)
                raw_radon_lta = await client.read_gatt_char(_UUID_RADON_LTA)
        except Exception as exc:
            mapped = ERROR_TYPE_MAP.get(type(exc))
            if mapped is not None:
                raise mapped(str(exc)) from exc
            raise BleReadError(str(exc)) from exc

        try:
            return AirthingsReading(
                temperature=struct.unpack("<h", raw_temp)[0] / 100.0,
                humidity=struct.unpack("<H", raw_hum)[0] / 100.0,
                radon_24h_avg=struct.unpack("<H", raw_radon_24h)[0],
                radon_long_term_avg=struct.unpack("<H", raw_radon_lta)[0],
            )
        except struct.error as exc:
            raise BleReadError(str(exc)) from exc
