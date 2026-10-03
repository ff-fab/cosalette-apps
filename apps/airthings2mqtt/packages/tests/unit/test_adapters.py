"""Unit tests for airthings2mqtt adapters — FakeAirthingsReader and
BleakAirthingsReader.

Test Techniques Used:
- Specification-based: Verify protocol compliance, default behavior, cycling
- State Transition: raise_on_next → read → error → cleared
- Error Guessing: BLE exception translation via ERROR_TYPE_MAP; health_check
  false when BLE adapter absent
- Decision Table: Wave-generation dispatch (2nd-gen characteristic present /
  absent) and the Wave 2 radon out-of-range guard
- Round-trip: Wave 2 decode over a captured real-device byte frame
- Equivalence Partitioning: pre-connect scan miss with zero vs. some advertisers
"""

from __future__ import annotations

import asyncio
import logging
import struct
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import (
    BleakBluetoothNotAvailableError,
    BleakBluetoothNotAvailableReason,
    BleakCharacteristicNotFoundError,
    BleakDBusError,
    BleakDeviceNotFoundError,
    BleakError,
)
from dbus_fast import Message, MessageType, Variant

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import (
    BleConnectionError,
    BleDeviceNotFoundError,
    BleReadError,
    BleTimeoutError,
)
from airthings2mqtt.ports import AirthingsReading
from tests.fixtures.ble import (
    WAVE2_SAMPLE_2950,
    WAVE2_SAMPLE_2950_DECODED,
    WAVE2_SAMPLE_2950_STATUS_BYTE_CLEARED,
)

_DEFAULT_ADVERTS = [("AA:BB:CC:DD:EE:FF", -71), ("40:79:12:16:A0:52", -64)]


@pytest.fixture(autouse=True)
def scanner() -> object:
    """Patch BleakScanner to "hear" ``scanner.adverts`` as (address, rssi) pairs.

    Defaults to every MAC this module reads, so the pre-connect scan finds the
    target; a test empties or replaces ``scanner.adverts`` to simulate a miss.
    """

    async def find_device_by_filter(
        filterfunc: object, timeout: float = 10.0
    ) -> BLEDevice | None:
        for address, rssi in fake.adverts:
            device = BLEDevice(address, None, None)
            if filterfunc(device, Mock(rssi=rssi)):  # type: ignore[operator]
                return device
        return None

    fake = Mock()
    fake.adverts = list(_DEFAULT_ADVERTS)
    fake.find_device_by_filter = AsyncMock(side_effect=find_device_by_filter)
    with patch("airthings2mqtt.adapters.bleak.BleakScanner", fake):
        yield fake


def _make_client(
    read_side_effect: object, *, wave2_char: object | None = None
) -> AsyncMock:
    """Build a mock BleakClient async context manager.

    Args:
        read_side_effect: ``side_effect`` for ``read_gatt_char``.
        wave2_char: what ``client.services.get_characteristic`` returns — the
            default ``None`` routes ``read()`` to the 1st-gen path.
    """
    client = AsyncMock()
    client.read_gatt_char = AsyncMock(side_effect=read_side_effect)
    client.services = Mock()
    client.services.get_characteristic = Mock(return_value=wave2_char)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.unit
class TestFakeAirthingsReaderHealthCheck:
    """Specification-based tests for FakeAirthingsReader.health_check."""

    async def test_health_check_returns_true(self) -> None:
        """health_check always returns True for the fake adapter.

        Technique: Specification-based — test double is unconditionally healthy.
        """
        reader = FakeAirthingsReader()

        result = await reader.health_check()

        assert result is True


@pytest.mark.unit
class TestFakeAirthingsReaderProtocol:
    """FakeAirthingsReader satisfies AirthingsReaderPort and HealthCheckable."""

    def test_isinstance_airthings_reader_port(self) -> None:
        """FakeAirthingsReader satisfies the AirthingsReaderPort protocol.

        Technique: Specification-based — PEP 544 runtime_checkable check.
        """
        from airthings2mqtt.ports import AirthingsReaderPort

        reader = FakeAirthingsReader()
        assert isinstance(reader, AirthingsReaderPort)

    def test_isinstance_health_checkable(self) -> None:
        """FakeAirthingsReader satisfies the HealthCheckable protocol.

        Technique: Specification-based — PEP 544 runtime_checkable check.
        """
        from cosalette import HealthCheckable

        reader = FakeAirthingsReader()
        assert isinstance(reader, HealthCheckable)


@pytest.mark.unit
class TestFakeAirthingsReader:
    """Verify FakeAirthingsReader satisfies AirthingsReaderPort protocol."""

    async def test_default_reading(self) -> None:
        """Default reading returns (21.5, 45.0, 80, 65) at -60 dBm."""
        reader = FakeAirthingsReader()
        reading = await reader.read("AA:BB:CC:DD:EE:FF")
        assert reading == AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
            rssi=-60,
        )

    async def test_stamps_last_read_on_every_read(self) -> None:
        """Each read carries the time it was taken, not the reading's creation.

        Technique: Specification-based — the cycled readings are module-level
        constants, so an unstamped one would publish a stale last_read.
        """
        reader = FakeAirthingsReader()
        before = datetime.now(UTC)
        first = await reader.read("AA:BB:CC:DD:EE:FF")
        second = await reader.read("AA:BB:CC:DD:EE:FF")
        assert before <= first.last_read <= second.last_read <= datetime.now(UTC)

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
class TestRedactMac:
    """Verify _redact_mac redacts BLE MACs without leaking the full identifier."""

    @pytest.mark.parametrize(
        "mac, expected",
        [
            ("AA:BB:CC:DD:EE:FF", "EE:FF"),  # standard colon format
            ("aa:bb:cc:dd:ee:ff", "ee:ff"),  # lowercase colon format
            ("AA-BB-CC-DD-EE-FF", "EE:FF"),  # dash-separated format
            ("AABBCCDDEEFF", "??:??"),  # no separator — placeholder
            ("abc", "??:??"),  # short/invalid — placeholder
            ("", "??:??"),  # empty — placeholder
        ],
    )
    def test_redact_mac(self, mac: str, expected: str) -> None:
        """_redact_mac shows last two octets for valid formats, placeholder otherwise.

        Technique: Equivalence Partitioning — colon format, dash format,
        separatorless hex, short/invalid, empty.
        """
        from airthings2mqtt.adapters.bleak import _redact_mac

        assert _redact_mac(mac) == expected


@pytest.mark.unit
class TestRedactMacsInText:
    """Verify redact_macs_in strips full MACs from free-form exception text.

    Technique: Equivalence Partitioning — colon, dash, BlueZ object-path
    underscore form, several MACs, and text without a MAC.
    """

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "Device with address AA:BB:CC:DD:EE:FF was not found.",
                "Device with address **:EE:FF was not found.",
            ),
            ("peer aa-bb-cc-dd-ee-ff gone", "peer **:ee:ff gone"),
            (
                "[org.bluez.Error.Failed] /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF",
                "[org.bluez.Error.Failed] /org/bluez/hci0/dev_**:EE:FF",
            ),
            ("11:22:33:44:55:66 and AA:BB:CC:DD:EE:FF", "**:55:66 and **:EE:FF"),
            ("uuid 00002a6e-0000-1000-8000-00805f9b34fb", None),  # not a MAC
            ("timed out", None),
        ],
    )
    def test_redacts_every_mac(self, text: str, expected: str | None) -> None:
        """Every MAC keeps only its last two octets; other text is unchanged."""
        from airthings2mqtt.adapters.bleak import redact_macs_in

        assert redact_macs_in(text) == (text if expected is None else expected)


@pytest.mark.unit
class TestBleakAirthingsReader:
    """Verify BleakAirthingsReader parses 1st-gen GATT data and translates errors."""

    @staticmethod
    def _encode_reading(
        temp: float = 21.5,
        hum: float = 45.0,
        radon_24h: int = 80,
        radon_lta: int = 65,
    ) -> dict[str, bytes]:
        """Encode sensor values as 1st-gen BLE GATT characteristic byte payloads."""
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
        mock_client = _make_client(lambda uuid: encoded[uuid])

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
            rssi=-71,
        )

    async def test_falls_through_to_1st_gen_when_wave2_char_absent(self) -> None:
        """A device without the 2nd-gen characteristic reads the four fixed chars.

        Technique: Decision Table — get_characteristic returns None → 1st-gen
        path; exactly the four 1st-gen UUIDs are read.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        encoded = self._encode_reading()
        mock_client = _make_client(lambda uuid: encoded[uuid], wave2_char=None)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            await reader.read("AA:BB:CC:DD:EE:FF")

        read_uuids = [c.args[0] for c in mock_client.read_gatt_char.call_args_list]
        assert read_uuids == list(encoded)

    async def test_logs_successful_read(self, caplog: pytest.LogCaptureFixture) -> None:
        """A successful read emits one INFO log with the MAC and parsed values.

        Technique: Specification-based — guards smoke-test finding A-3 (a
        successful BLE read produced no log line, making the data path invisible
        from logs alone).
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        encoded = self._encode_reading(temp=21.5, hum=45.0, radon_24h=80, radon_lta=65)
        mock_client = _make_client(lambda uuid: encoded[uuid])

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with caplog.at_level(logging.INFO, logger="airthings2mqtt.adapters.bleak"):
                await reader.read("AA:BB:CC:DD:EE:FF")

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        # Use existence check rather than exact count: future adapter instrumentation
        # adding extra INFO lines won't cause a spurious failure here.
        assert info_records, "Expected at least one INFO log record on successful read"
        message = info_records[0].getMessage()
        # Full redacted token guards both the **:prefix and the last-octet suffix.
        assert "mac=**:EE:FF" in message
        assert "AA:BB:CC:DD:EE:FF" not in message
        # Key-presence assertions; avoids coupling to the exact %-format precision
        # so log-format tweaks don't break this test.
        assert "protocol=wave1" in message
        assert "temperature=" in message
        assert "humidity=" in message
        assert "radon_24h_avg=" in message
        assert "radon_long_term_avg=" in message

    async def test_translates_connection_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ConnectionError is translated to BleConnectionError; no INFO log on error.

        Technique: Error Guessing + Condition Coverage — error path exits before
        the logger.info call so the success log is suppressed on failure.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with (
                caplog.at_level(logging.INFO, logger="airthings2mqtt.adapters.bleak"),
                pytest.raises(BleConnectionError, match="refused"),
            ):
                await reader.read("AA:BB:CC:DD:EE:FF")

        info_logs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert not info_logs, "No INFO log should be emitted when a BLE error occurs"

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

    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (
                BleakDeviceNotFoundError("AA:BB:CC:DD:EE:FF", "not found"),
                BleDeviceNotFoundError,
            ),
            (
                BleakBluetoothNotAvailableError(
                    "off", BleakBluetoothNotAvailableReason.POWERED_OFF
                ),
                BleConnectionError,
            ),
            (BleakDBusError("org.bluez.Error.Failed", ["abort"]), BleConnectionError),
            (ConnectionRefusedError("refused"), BleConnectionError),
            (BleakCharacteristicNotFoundError("2a6e"), BleReadError),
            (BleakError("other"), BleReadError),
        ],
    )
    async def test_translates_bleak_errors_by_mro(
        self, exc: Exception, expected: type[Exception]
    ) -> None:
        """bleak and stdlib subclasses map to the closest domain error.

        Technique: Decision Table — incident 2 (BleakDeviceNotFoundError fell
        through the exact-type lookup to non-retryable BleReadError).
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=exc)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
            ),
            pytest.raises(expected) as raised,
        ):
            await BleakAirthingsReader().read("AA:BB:CC:DD:EE:FF")

        assert type(raised.value) is expected
        assert raised.value.__cause__ is exc

    async def test_device_not_found_message_carries_no_full_mac(self) -> None:
        """bleak's not-found text is redacted and its chain hidden from logs.

        Technique: Error Guessing — incident 2 published the full MAC on the
        broker-visible error topic; the cause's traceback would leak it too.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mac = "AA:BB:CC:DD:EE:FF"
        exc = BleakDeviceNotFoundError(mac, f"Device with address {mac} was not found.")
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(side_effect=exc)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
            ),
            pytest.raises(BleDeviceNotFoundError) as raised,
        ):
            await BleakAirthingsReader().read(mac)

        assert str(raised.value) == (
            "BleakDeviceNotFoundError: Device with address **:EE:FF was not found."
        )
        assert raised.value.__suppress_context__
        assert raised.value.__cause__ is None

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
        mock_client = _make_client(lambda uuid: payloads[uuid])

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
        mock_client = _make_client(lambda uuid: encoded[uuid])

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            reading = await reader.read("AA:BB:CC:DD:EE:FF")

        assert reading.temperature == -5.0


@pytest.mark.unit
class TestBleakAirthingsReaderScan:
    """Verify the pre-connect advertiser scan (proposal 5.9, cap-oxdp.5)."""

    @pytest.mark.parametrize(
        ("adverts", "expected"),
        [
            ([], "0 advertisers in 10s (no advertisements observed during scan)"),
            (
                [("11:22:33:44:55:66", -80), ("11:22:33:44:55:77", -90)],
                "2 advertisers in 10s (other addresses observed; target not observed)",
            ),
            (
                [
                    ("11:22:33:44:55:66", -80),
                    ("11:22:33:44:55:66", -75),
                    ("11:22:33:44:55:77", -90),
                ],
                "2 advertisers in 10s (other addresses observed; target not observed)",
            ),
        ],
    )
    async def test_miss_reports_distinct_advertiser_count(
        self, scanner: Mock, adverts: list[tuple[str, int]], expected: str
    ) -> None:
        """A miss reports how many distinct advertiser addresses were observed.

        Technique: Equivalence Partitioning — no advertisements vs. one or more
        distinct other addresses; no connect is attempted in either case.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        scanner.adverts = adverts
        with (
            patch("airthings2mqtt.adapters.bleak.BleakClient") as client_cls,
            pytest.raises(BleDeviceNotFoundError) as raised,
        ):
            await BleakAirthingsReader().read("AA:BB:CC:DD:EE:FF")

        assert str(raised.value) == f"target not seen; {expected}"
        client_cls.assert_not_called()

    async def test_connects_to_scanned_device_within_scan_timeout(
        self, scanner: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The found BLEDevice goes to BleakClient; its RSSI reaches the read log.

        Technique: Specification-based — a lower-case configured MAC still
        matches, the scan honours ``scan_timeout``, and the client skips its
        own internal scan.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = _make_client(lambda _uuid: WAVE2_SAMPLE_2950, wave2_char=object())
        with (
            patch(
                "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
            ) as client_cls,
            caplog.at_level(logging.INFO, logger="airthings2mqtt.adapters.bleak"),
        ):
            await BleakAirthingsReader(scan_timeout=7.5).read("40:79:12:16:a0:52")

        (device,) = client_cls.call_args.args
        assert isinstance(device, BLEDevice)
        assert device.address == "40:79:12:16:A0:52"
        assert scanner.find_device_by_filter.call_args.kwargs["timeout"] == 7.5
        assert "rssi=-64" in caplog.records[-1].getMessage()

    async def test_scan_failure_is_translated(self, scanner: Mock) -> None:
        """A powered-off adapter during the scan becomes BleConnectionError.

        Technique: Error Guessing — scanner errors share read()'s translation.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        scanner.find_device_by_filter.side_effect = BleakBluetoothNotAvailableError(
            "off", BleakBluetoothNotAvailableReason.POWERED_OFF
        )
        with pytest.raises(BleConnectionError):
            await BleakAirthingsReader().read("AA:BB:CC:DD:EE:FF")

    async def test_scan_cancellation_propagates_without_connecting(
        self, scanner: Mock
    ) -> None:
        """Scanner cancellation propagates unchanged before any BLE connection.

        Technique: Error Guessing — cancellation must not become a read error.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        cancellation = asyncio.CancelledError("scan cancelled")
        scanner.find_device_by_filter.side_effect = cancellation
        with (
            patch("airthings2mqtt.adapters.bleak.BleakClient") as client_cls,
            pytest.raises(asyncio.CancelledError) as raised,
        ):
            await BleakAirthingsReader().read("AA:BB:CC:DD:EE:FF")

        assert raised.value is cancellation
        client_cls.assert_not_called()


@pytest.mark.unit
class TestBleakAirthingsReaderWave2:
    """Verify the Wave 2 / Wave Radon (2nd-gen) single-characteristic path."""

    async def test_reads_wave2_char_when_present(self) -> None:
        """When get_characteristic finds b42e4dcc, only that char is read.

        Technique: Decision Table — 2nd-gen characteristic present → Wave 2
        path; the four 1st-gen UUIDs are never read.
        """
        from airthings2mqtt.adapters.bleak import (
            _UUID_WAVE2_DATA,
            BleakAirthingsReader,
        )

        mock_client = _make_client(lambda _uuid: WAVE2_SAMPLE_2950, wave2_char=object())

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            reading = await reader.read("40:79:12:16:A0:52")

        read_uuids = [c.args[0] for c in mock_client.read_gatt_char.call_args_list]
        assert read_uuids == [_UUID_WAVE2_DATA]
        assert reading == AirthingsReading(**WAVE2_SAMPLE_2950_DECODED, rssi=-64)

    async def test_decodes_captured_real_device_frame(self) -> None:
        """Decoded values match the ff-fab field capture cross-check.

        Technique: Round-trip — a real 20-byte frame from an Airthings Wave2
        (model 2950) decodes to the humidity / radon / temperature the capture
        verified against the official app.
        """
        from airthings2mqtt.adapters.bleak import _parse_wave2

        reading = _parse_wave2(WAVE2_SAMPLE_2950)

        assert reading == AirthingsReading(
            temperature=33.31,
            humidity=33.5,
            radon_24h_avg=134,
            radon_long_term_avg=106,
        )

    async def test_ignores_status_byte_toggle(self) -> None:
        """val[2] (status/ambient-light byte) is not surfaced as a measurement.

        Technique: Specification-based — the capture's second read differs only
        in byte 2; the decoded reading must be identical.
        """
        from airthings2mqtt.adapters.bleak import _parse_wave2

        assert _parse_wave2(WAVE2_SAMPLE_2950) == _parse_wave2(
            WAVE2_SAMPLE_2950_STATUS_BYTE_CLEARED
        )

    @pytest.mark.parametrize(
        "radon_raw, expected",
        [
            (0, 0),  # lower bound — valid
            (16383, 16383),  # upper bound — valid
            (16384, None),  # one past the bound — dropped
            (0xFFFF, None),  # "not fitted" sentinel — dropped
        ],
    )
    async def test_radon_out_of_range_becomes_none(
        self, radon_raw: int, expected: int | None
    ) -> None:
        """Radon outside 0–16383 decodes to None rather than a false spike.

        Technique: Boundary Value Analysis — the community airthings-ble
        sanity bound applied at both edges.
        """
        from airthings2mqtt.adapters.bleak import _parse_wave2

        frame = struct.pack(
            "<4B8H", 1, 67, 0, 0, radon_raw, radon_raw, 3331, *([0] * 5)
        )

        reading = _parse_wave2(frame)

        assert reading.radon_24h_avg == expected
        assert reading.radon_long_term_avg == expected

    async def test_short_wave2_frame_raises_ble_read_error(self) -> None:
        """A frame shorter than 20 bytes triggers struct.error → BleReadError.

        Technique: Error Guessing — device returns a truncated read.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = _make_client(
            lambda _uuid: WAVE2_SAMPLE_2950[:12], wave2_char=object()
        )

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with pytest.raises(BleReadError):
                await reader.read("40:79:12:16:A0:52")

    async def test_logs_wave2_protocol(self, caplog: pytest.LogCaptureFixture) -> None:
        """The success log records protocol=wave2 on the 2nd-gen path.

        Technique: Specification-based — the log line must distinguish which
        GATT layout produced the reading.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        mock_client = _make_client(lambda _uuid: WAVE2_SAMPLE_2950, wave2_char=object())

        with patch(
            "airthings2mqtt.adapters.bleak.BleakClient", return_value=mock_client
        ):
            reader = BleakAirthingsReader()
            with caplog.at_level(logging.INFO, logger="airthings2mqtt.adapters.bleak"):
                await reader.read("40:79:12:16:A0:52")

        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert info_records
        assert "protocol=wave2" in info_records[0].getMessage()


@pytest.mark.unit
class TestBleakAirthingsReaderHealthCheck:
    """Verify health_check reads BlueZ's hci0 Powered property over D-Bus."""

    @staticmethod
    def _bus_with_reply(reply: Message) -> AsyncMock:
        bus = AsyncMock()
        bus.connect = AsyncMock(return_value=bus)
        bus.call = AsyncMock(return_value=reply)
        bus.disconnect = Mock()
        return bus

    @staticmethod
    def _reply(powered: bool) -> Message:
        return Message(
            message_type=MessageType.METHOD_RETURN,
            reply_serial=1,
            signature="v",
            body=[Variant("b", powered)],
        )

    async def test_returns_true_only_when_bluez_reports_powered(self) -> None:
        """A successful boolean Powered=true reply is healthy."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(True))
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is True
        request = bus.call.call_args.args[0]
        assert request.destination == "org.bluez"
        assert request.path == "/org/bluez/hci0"
        assert request.interface == "org.freedesktop.DBus.Properties"
        assert request.member == "Get"
        assert request.body == ["org.bluez.Adapter1", "Powered"]

    async def test_returns_false_when_adapter_is_unpowered(self) -> None:
        """A valid Powered=false reply is unhealthy."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(False))
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is False

    async def test_returns_false_when_connection_fails(self) -> None:
        """Failure to connect to the system bus is unhealthy and cleaned up."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(True))
        bus.connect.side_effect = ConnectionError("system bus unavailable")
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is False
        bus.disconnect.assert_called_once_with()

    async def test_returns_false_when_bus_construction_fails(self) -> None:
        """A synchronous system-bus construction failure cannot escape."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        with patch(
            "airthings2mqtt.adapters.bleak.MessageBus",
            side_effect=RuntimeError("invalid system bus address"),
        ):
            result = await BleakAirthingsReader().health_check()

        assert result is False

    async def test_returns_false_for_dbus_error_reply(self) -> None:
        """A BlueZ D-Bus error reply is unhealthy."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        reply = Mock(message_type=MessageType.ERROR, body=[])
        bus = self._bus_with_reply(reply)
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is False

    @pytest.mark.parametrize(
        "body",
        [
            None,
            [],
            (Variant("b", True),),
            [True],
            [Variant("s", "true")],
            [Variant("b", True), Variant("b", True)],
        ],
    )
    async def test_returns_false_for_malformed_reply(self, body: object) -> None:
        """Missing, unwrapped, mistyped, and extra property values are unhealthy."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        reply = Mock(message_type=MessageType.METHOD_RETURN, body=body)
        bus = self._bus_with_reply(reply)
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is False

    async def test_returns_false_when_probe_times_out(self) -> None:
        """The D-Bus probe is bounded and disconnects after cancellation."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(True))

        async def wait_forever(_message: Message) -> None:
            await asyncio.Event().wait()

        bus.call.side_effect = wait_forever
        with (
            patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus),
            patch("airthings2mqtt.adapters.bleak._HEALTH_CHECK_TIMEOUT_SECONDS", 0.001),
        ):
            result = await BleakAirthingsReader().health_check()

        assert result is False
        bus.disconnect.assert_called_once_with()

    async def test_returns_false_when_disconnect_fails(self) -> None:
        """Cleanup failure makes the probe unhealthy without escaping."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(True))
        bus.disconnect.side_effect = RuntimeError("disconnect failed")
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            result = await BleakAirthingsReader().health_check()

        assert result is False

    async def test_disconnects_after_successful_probe(self) -> None:
        """The short-lived system bus is disconnected after a successful reply."""
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        bus = self._bus_with_reply(self._reply(True))
        with patch("airthings2mqtt.adapters.bleak.MessageBus", return_value=bus):
            await BleakAirthingsReader().health_check()

        bus.disconnect.assert_called_once_with()

    def test_isinstance_health_checkable(self) -> None:
        """BleakAirthingsReader satisfies the HealthCheckable protocol.

        Technique: Specification-based — PEP 544 runtime_checkable check.
        """
        from cosalette import HealthCheckable

        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        reader = BleakAirthingsReader()
        assert isinstance(reader, HealthCheckable)
