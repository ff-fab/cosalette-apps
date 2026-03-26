"""Unit tests for airthings2mqtt adapters — FakeAirthingsReader and BleakAirthingsReader.

Test Techniques Used:
- Specification-based: Verify protocol compliance, default behavior, cycling
- State Transition: raise_on_next → read → error → cleared
- Error Guessing: BLE exception translation via ERROR_TYPE_MAP
"""

from __future__ import annotations

import struct
from unittest.mock import AsyncMock, patch

import pytest

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError, BleReadError, BleTimeoutError
from airthings2mqtt.ports import AirthingsReading


@pytest.mark.unit
class TestFakeAirthingsReader:
    """Verify FakeAirthingsReader satisfies AirthingsReaderPort protocol."""

    async def test_default_reading(self) -> None:
        """Default reading returns (21.5, 45.0, 80, 65)."""
        reader = FakeAirthingsReader()
        reading = await reader.read("AA:BB:CC:DD:EE:FF")
        assert reading == AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
        )

    async def test_records_mac_address(self) -> None:
        """read() records the MAC address passed."""
        reader = FakeAirthingsReader()
        await reader.read("11:22:33:44:55:66")
        assert reader.calls == ["11:22:33:44:55:66"]

    async def test_cycling_through_readings(self) -> None:
        """Reader cycles through provided readings."""
        readings = [
            AirthingsReading(
                temperature=20.0,
                humidity=40.0,
                radon_24h_avg=50,
                radon_long_term_avg=45,
            ),
            AirthingsReading(
                temperature=22.0,
                humidity=50.0,
                radon_24h_avg=90,
                radon_long_term_avg=70,
            ),
        ]
        reader = FakeAirthingsReader()
        reader.readings = readings

        first = await reader.read("AA:BB:CC:DD:EE:FF")
        second = await reader.read("AA:BB:CC:DD:EE:FF")
        third = await reader.read("AA:BB:CC:DD:EE:FF")

        assert first == readings[0]
        assert second == readings[1]
        assert third == readings[0]  # cycles back

    async def test_raise_on_next(self) -> None:
        """raise_on_next causes the next read to raise, then clears.

        Technique: State Transition — error state is transient.
        """
        reader = FakeAirthingsReader()
        reader.raise_on_next = BleConnectionError("device unreachable")

        with pytest.raises(BleConnectionError, match="device unreachable"):
            await reader.read("AA:BB:CC:DD:EE:FF")

        # Subsequent read succeeds
        reading = await reader.read("AA:BB:CC:DD:EE:FF")
        assert reading.temperature == 21.5

    async def test_raise_on_next_records_call(self) -> None:
        """MAC address is recorded even when raise_on_next fires."""
        reader = FakeAirthingsReader()
        reader.raise_on_next = BleReadError("read failed")

        with pytest.raises(BleReadError):
            await reader.read("AA:BB:CC:DD:EE:FF")

        assert reader.calls == ["AA:BB:CC:DD:EE:FF"]


@pytest.mark.unit
class TestBleakAirthingsReader:
    """Verify BleakAirthingsReader parses GATT data and translates errors."""

    @staticmethod
    def _encode_reading(
        temp: float = 21.5,
        hum: float = 45.0,
        radon_24h: int = 80,
        radon_lta: int = 65,
    ) -> dict[str, bytes]:
        """Encode sensor values as BLE GATT characteristic byte payloads."""
        return {
            "00002a6e-0000-1000-8000-00805f9b34fb": struct.pack("<h", int(temp * 100)),
            "00002a6f-0000-1000-8000-00805f9b34fb": struct.pack("<H", int(hum * 100)),
            "b42e01aa-ade7-11e4-89d3-123b93f75cba": struct.pack("<H", radon_24h),
            "b42e0a4c-ade7-11e4-89d3-123b93f75cba": struct.pack("<H", radon_lta),
        }

    async def test_parses_gatt_values(self) -> None:
        """Correctly parses temperature, humidity, and radon from GATT bytes."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        encoded = self._encode_reading(temp=21.5, hum=45.0, radon_24h=80, radon_lta=65)
        mock_client = AsyncMock()
        mock_client.read_gatt_char = AsyncMock(side_effect=lambda uuid: encoded[uuid])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            reading = await reader.read("AA:BB:CC:DD:EE:FF")

        assert reading == AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
        )

    async def test_translates_connection_error(self) -> None:
        """ConnectionError is translated to BleConnectionError."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with pytest.raises(BleConnectionError, match="refused"):
                await reader.read("AA:BB:CC:DD:EE:FF")

    async def test_translates_timeout_error(self) -> None:
        """TimeoutError is translated to BleTimeoutError."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=TimeoutError("timed out"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with pytest.raises(BleTimeoutError, match="timed out"):
                await reader.read("AA:BB:CC:DD:EE:FF")

    async def test_unmapped_error_becomes_ble_read_error(self) -> None:
        """Unmapped exceptions become BleReadError."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ValueError("unexpected"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with pytest.raises(BleReadError, match="unexpected"):
                await reader.read("AA:BB:CC:DD:EE:FF")

    async def test_malformed_payload_raises_ble_read_error(self) -> None:
        """Truncated GATT payload triggers struct.error → BleReadError.

        Technique: Error Guessing — device returns fewer bytes than expected.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        # Return only 1 byte for temperature (needs 2 for "<h")
        payloads = {
            "00002a6e-0000-1000-8000-00805f9b34fb": b"\x01",
            "00002a6f-0000-1000-8000-00805f9b34fb": struct.pack("<H", 4500),
            "b42e01aa-ade7-11e4-89d3-123b93f75cba": struct.pack("<H", 80),
            "b42e0a4c-ade7-11e4-89d3-123b93f75cba": struct.pack("<H", 65),
        }
        mock_client = AsyncMock()
        mock_client.read_gatt_char = AsyncMock(side_effect=lambda uuid: payloads[uuid])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with pytest.raises(BleReadError):
                await reader.read("AA:BB:CC:DD:EE:FF")

    async def test_negative_temperature(self) -> None:
        """Signed short correctly represents negative temperatures."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        encoded = self._encode_reading(
            temp=-5.0, hum=80.0, radon_24h=120, radon_lta=100
        )
        mock_client = AsyncMock()
        mock_client.read_gatt_char = AsyncMock(side_effect=lambda uuid: encoded[uuid])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            reading = await reader.read("AA:BB:CC:DD:EE:FF")

        assert reading.temperature == -5.0
