"""Bleak-based BLE adapter for Airthings Wave sensors.

Connects to an Airthings Wave device via BLE and returns an
:class:`AirthingsReading`. Two GATT layouts are supported, auto-detected per
connection:

* **Wave (1st-gen)** — four fixed characteristic reads (temperature, humidity,
  radon 24h, radon long-term).
* **Wave 2 / Wave Radon (2nd-gen)** — a single read of the proprietary
  "current values" characteristic ``b42e4dcc-…``, decoded with ``<4B8H``.

The 2nd-gen characteristic is probed first; a device that lacks it falls
through to the unchanged 1st-gen path. Field maps follow the community
``airthings-ble`` decoder — see ``docs/planning/wave2-protocol-support.md``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import struct
from collections.abc import Buffer

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import (
    BleakBluetoothNotAvailableError,
    BleakDBusError,
    BleakDeviceNotFoundError,
)
from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from airthings2mqtt.errors import (
    ERROR_TYPE_MAP,
    AirthingsError,
    BleConnectionError,
    BleDeviceNotFoundError,
    map_exception,
)
from airthings2mqtt.ports import AirthingsReading

# BLE GATT characteristic UUIDs — Wave (1st-gen)
_UUID_TEMPERATURE = "00002a6e-0000-1000-8000-00805f9b34fb"
_UUID_HUMIDITY = "00002a6f-0000-1000-8000-00805f9b34fb"
_UUID_RADON_24H = "b42e01aa-ade7-11e4-89d3-123b93f75cba"
_UUID_RADON_LTA = "b42e0a4c-ade7-11e4-89d3-123b93f75cba"

# BLE GATT characteristic UUID — Wave 2 / Wave Radon (2nd-gen) "current values"
_UUID_WAVE2_DATA = "b42e4dcc-ade7-11e4-89d3-123b93f75cba"

_WAVE2_STRUCT = "<4B8H"
"""20-byte Wave 2 frame: 4 uint8 then 8 uint16, little-endian."""

_RADON_MAX = 16383
"""Upper bound on a plausible radon reading (Bq/m³).

Matches the community ``airthings-ble`` library's own sanity check. A garbled
Wave 2 frame that unpacks to a wild uint16 (``0xFFFF`` == 65535) is dropped to
``None`` rather than published as a false radon spike.
"""

_BLEAK_ERROR_MAP: dict[type[BaseException], type[AirthingsError]] = {
    **ERROR_TYPE_MAP,
    BleakDeviceNotFoundError: BleDeviceNotFoundError,
    BleakBluetoothNotAvailableError: BleConnectionError,
    BleakDBusError: BleConnectionError,
}
"""bleak-specific additions to :data:`~airthings2mqtt.errors.ERROR_TYPE_MAP`.

A vanished device must be retried and, once retries are exhausted, marked
offline; as a plain ``BleakError`` it would fall through to the non-retryable
``BleReadError``. Every other ``BleakError`` (e.g. a missing characteristic
on a non-Airthings device) stays ``BleReadError``.
"""

SCAN_TIMEOUT_SECONDS = 10.0
"""Upper bound on the pre-connect advertiser scan and its default duration."""

_BLUEZ_ADAPTER_PATH = "/org/bluez/hci0"
_HEALTH_CHECK_TIMEOUT_SECONDS = 5.0

logger = logging.getLogger(__name__)


def _redact_mac(mac: str) -> str:
    """Return a redacted form of *mac* showing only the last two octets.

    Supports colon-separated (``AA:BB:CC:DD:EE:FF``) and dash-separated
    (``AA-BB-CC-DD-EE-FF``) formats.  For any unrecognised format returns
    ``??:??`` so the full configured value is never echoed in logs.
    """
    for sep in (":", "-"):
        parts = mac.split(sep)
        if len(parts) == 6:  # standard MAC: 6 octets with 5 separators
            return f"{parts[-2]}:{parts[-1]}"
    return "??:??"


_MAC_IN_TEXT = re.compile(
    r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[:_-]){4}"
    r"([0-9A-Fa-f]{2})[:_-]([0-9A-Fa-f]{2})(?![0-9A-Fa-f])"
)
"""A MAC inside free text: colon, dash, or BlueZ object-path underscore form."""


def _redact_macs_in(text: str) -> str:
    """Replace every MAC in *text* with ``**:EE:FF`` (its last two octets).

    bleak and BlueZ embed the full address in exception text (``Device with
    address AA:BB:… was not found``, ``/org/bluez/hci0/dev_AA_BB_…``), which
    would otherwise reach the logs and the broker-visible error topic.
    """
    return _MAC_IN_TEXT.sub(lambda m: f"**:{m[1]}:{m[2]}", text)


def _bounded_radon(value: int) -> int | None:
    """Return *value* Bq/m³, or ``None`` when outside the plausible 0–16383 range."""
    return value if 0 <= value <= _RADON_MAX else None


def _parse_wave1(
    raw_temp: Buffer,
    raw_hum: Buffer,
    raw_radon_24h: Buffer,
    raw_radon_lta: Buffer,
) -> AirthingsReading:
    """Decode the four 1st-gen Wave GATT characteristic reads."""
    return AirthingsReading(
        temperature=struct.unpack("<h", raw_temp)[0] / 100.0,
        humidity=struct.unpack("<H", raw_hum)[0] / 100.0,
        radon_24h_avg=struct.unpack("<H", raw_radon_24h)[0],
        radon_long_term_avg=struct.unpack("<H", raw_radon_lta)[0],
    )


def _parse_wave2(raw: Buffer) -> AirthingsReading:
    """Decode the Wave 2 / Wave Radon (2nd-gen) "current values" characteristic.

    20 bytes, ``<4B8H``.  Only humidity (``val[1]``), radon short/long-term
    (``val[4]``/``val[5]``) and temperature (``val[6]``) are fitted on this
    hardware; the trailing shorts are Wave Plus slots left at ``0xFFFF``.
    ``val[0]`` is a format-version byte, logged at DEBUG so a future firmware
    layout change is visible.  Radon is bounds-checked (:func:`_bounded_radon`);
    temperature and humidity mirror the 1st-gen path and are passed through
    unbounded.
    """
    val = struct.unpack(_WAVE2_STRUCT, raw)
    logger.debug(
        "Wave 2 frame: format_version=%d raw=%s", val[0], memoryview(raw).hex(" ")
    )
    return AirthingsReading(
        temperature=val[6] / 100.0,
        humidity=val[1] / 2.0,
        radon_24h_avg=_bounded_radon(val[4]),
        radon_long_term_avg=_bounded_radon(val[5]),
    )


class BleakAirthingsReader:
    """Production adapter for reading Airthings Wave sensors via Bleak.

    Connects to the device, reads the GATT characteristics for its Wave
    generation, disconnects, and returns the parsed AirthingsReading. Each
    read() call is a full scan-connect-read-disconnect cycle.

    Args:
        scan_timeout: Seconds the pre-connect scan listens for the target's
            advertisement; ``main`` keeps it well inside ``poll_timeout``.
    """

    def __init__(self, scan_timeout: float = SCAN_TIMEOUT_SECONDS) -> None:
        self._scan_timeout = scan_timeout

    async def health_check(self) -> bool:
        """Probe whether BlueZ reports the hci0 adapter as powered.

        Returns:
            True only when BlueZ returns a boolean ``Powered=true`` property;
            False for unavailable, unpowered, malformed, or timed-out probes.
        """
        try:
            return await asyncio.wait_for(
                self._probe_adapter_powered(),
                timeout=_HEALTH_CHECK_TIMEOUT_SECONDS,
            )
        except Exception:
            return False

    @staticmethod
    async def _probe_adapter_powered() -> bool:
        """Query BlueZ using one bounded, safely cleaned-up bus lifecycle."""
        bus: MessageBus | None = None
        healthy = False
        try:
            # dbus-fast binds MessageBus to the running loop, so construction
            # and all public bus operations belong in this probe coroutine.
            bus = MessageBus(bus_type=BusType.SYSTEM)
            await bus.connect()
            reply: Message = await bus.call(
                Message(
                    destination="org.bluez",
                    path=_BLUEZ_ADAPTER_PATH,
                    interface="org.freedesktop.DBus.Properties",
                    member="Get",
                    signature="ss",
                    body=["org.bluez.Adapter1", "Powered"],
                )
            )
            body = reply.body
            if (
                reply.message_type is not MessageType.METHOD_RETURN
                or not isinstance(body, list)
                or len(body) != 1
            ):
                healthy = False
            else:
                powered = body[0]
                healthy = (
                    isinstance(powered, Variant)
                    and powered.signature == "b"
                    and powered.value is True
                )
        except Exception:
            healthy = False
        finally:
            if bus is not None:
                try:
                    bus.disconnect()
                except Exception:
                    healthy = False
        return healthy

    async def _scan(self, mac: str) -> tuple[BLEDevice, int]:
        """Listen for *mac*'s advertisement; return the device and its RSSI (dBm).

        Counting distinct advertiser addresses records whether any other
        advertisements were observed during the scan. Handing the found
        :class:`BLEDevice` to :class:`BleakClient` spares it a second scan.

        Raises:
            BleDeviceNotFoundError: If the target did not advertise in time.
        """
        heard: dict[str, int] = {}

        def _is_target(device: BLEDevice, adv: AdvertisementData) -> bool:
            heard[device.address] = adv.rssi
            return device.address.upper() == mac.upper()

        timeout = self._scan_timeout
        device = await BleakScanner.find_device_by_filter(_is_target, timeout=timeout)
        if device is None:
            hint = (
                "no advertisements observed during scan"
                if not heard
                else "other addresses observed; target not observed"
            )
            raise BleDeviceNotFoundError(
                f"target not seen; {len(heard)} advertisers in {timeout:g}s ({hint})"
            )
        return device, heard[device.address]

    async def read(self, mac: str) -> AirthingsReading:
        """Read sensor data from the Airthings Wave device.

        Scans for the device first (see :meth:`_scan`), then probes for the
        Wave 2 / Wave Radon (2nd-gen) "current values" characteristic and reads
        it if present; otherwise falls through to the 1st-gen
        four-characteristic path.

        Args:
            mac: Bluetooth MAC address of the Airthings Wave device.

        Returns:
            AirthingsReading with parsed sensor values.

        Raises:
            BleConnectionError: If the device cannot be reached
                (:class:`BleDeviceNotFoundError` when it is not seen at all).
            BleReadError: If a GATT characteristic cannot be read or decoded.
            BleTimeoutError: If the connection or read times out.
        """
        try:
            device, rssi = await self._scan(mac)
            async with BleakClient(device) as client:
                if client.services.get_characteristic(_UUID_WAVE2_DATA) is not None:
                    protocol = "wave2"
                    reading = _parse_wave2(
                        await client.read_gatt_char(_UUID_WAVE2_DATA)
                    )
                else:
                    protocol = "wave1"
                    reading = _parse_wave1(
                        await client.read_gatt_char(_UUID_TEMPERATURE),
                        await client.read_gatt_char(_UUID_HUMIDITY),
                        await client.read_gatt_char(_UUID_RADON_24H),
                        await client.read_gatt_char(_UUID_RADON_LTA),
                    )
        except AirthingsError:
            raise
        except Exception as exc:
            # struct.error from a malformed frame is unmapped → BleReadError.
            error = map_exception(exc, _BLEAK_ERROR_MAP)
            message = _redact_macs_in(str(exc))
            if message == str(exc):
                raise error(message) from exc
            # The cause's own text (logged with the traceback) carries the full
            # MAC, so drop the chain and keep only its class name.
            raise error(f"{type(exc).__name__}: {message}") from None

        logger.info(
            "Airthings read ok: mac=**:%s rssi=%d protocol=%s temperature=%.2f "
            "humidity=%.2f radon_24h_avg=%s radon_long_term_avg=%s",
            _redact_mac(mac),
            rssi,
            protocol,
            reading.temperature,
            reading.humidity,
            reading.radon_24h_avg,
            reading.radon_long_term_avg,
        )
        return reading
