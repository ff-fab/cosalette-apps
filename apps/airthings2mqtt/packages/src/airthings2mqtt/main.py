"""airthings2mqtt application entry point.

Wires the cosalette App with the Airthings BLE telemetry device,
adapter, and settings.  The ``main()`` function is the CLI entry point.
"""

from __future__ import annotations

import asyncio
import logging
import weakref

import cosalette
from cosalette import setting_ref

from airthings2mqtt import __version__
from airthings2mqtt.adapters.bleak import BleakAirthingsReader
from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import (
    BleConnectionError,
    BleTimeoutError,
    error_type_map,
)
from airthings2mqtt.ports import AirthingsReaderPort, AirthingsReading
from airthings2mqtt.settings import Airthings2MqttSettings

app = cosalette.App(
    name="airthings2mqtt",
    version=__version__,
    settings_class=Airthings2MqttSettings,
    adapters={
        AirthingsReaderPort: (BleakAirthingsReader, FakeAirthingsReader),
    },
    restart_after_failures=5,
    max_restarts=3,
    error_type_map=error_type_map,
)

# ADR-004: runtime HA discovery
app.discovery()

_read_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)
"""One lock per running event loop.

Production uses a single loop so reads are serialized as expected.
In pytest each function-scoped loop gets its own fresh lock with no
cross-test state leakage. The WeakKeyDictionary releases locks when
their loop is garbage-collected, preventing memory growth.
"""


def _get_read_lock() -> asyncio.Lock:
    """Return the serialization lock bound to the current running loop."""
    loop = asyncio.get_running_loop()
    lock = _read_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _read_locks[loop] = lock
    return lock


_TRIGGER_MIN_INTERVAL_SECONDS: float = 30.0
"""Minimum spacing between trigger-initiated reads (cosalette ADR-066).

A BLE connect/read to the Airthings takes seconds and drains a battery-powered
sensor, and ``airthings2mqtt/airthings/set`` is a public MQTT topic - a dashboard
button held down, or an automation loop, would otherwise queue one round-trip per
message. A wake inside a closed window is *held*, not dropped, so the re-read
still happens; it just waits for the window to reopen. Well under the default
``poll_interval`` so it never throttles the scheduled cadence.
"""


@app.telemetry(
    "airthings",
    interval=setting_ref("poll_interval"),
    timeout=setting_ref("poll_timeout"),
    triggerable=True,
    min_interval=_TRIGGER_MIN_INTERVAL_SECONDS,
    retry=3,
    retry_on=(BleConnectionError, BleTimeoutError, TimeoutError),
    summary="Read Airthings BLE sensor values (temperature, humidity, radon)",
    state_model=AirthingsReading,
)
async def _telemetry(
    reader: AirthingsReaderPort,
    settings: Airthings2MqttSettings,
    trigger: cosalette.TriggerPayload,
    logger: logging.Logger,
) -> dict[str, object]:
    """Read all sensor values and return state dict."""
    if trigger.is_triggered:
        logger.info("On-demand Airthings re-read triggered")

    async with _get_read_lock():
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
