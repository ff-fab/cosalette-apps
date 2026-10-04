"""airthings2mqtt application entry point.

Wires the cosalette App with the Airthings BLE telemetry device,
adapter, and settings.  The ``main()`` function is the CLI entry point.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from dataclasses import replace
from datetime import timedelta

import cosalette
from cosalette import DeviceStore, SaveOnChange, setting_ref

from airthings2mqtt import __version__
from airthings2mqtt.adapters.bleak import (
    SCAN_TIMEOUT_SECONDS,
    BleakAirthingsReader,
    redact_macs_in,
)
from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import (
    BleConnectionError,
    BleReadError,
    BleTimeoutError,
    error_type_map,
)
from airthings2mqtt.lifecycle import ResetState, track
from airthings2mqtt.ports import AirthingsReaderPort, AirthingsReading
from airthings2mqtt.settings import Airthings2MqttSettings


def _make_reader(settings: Airthings2MqttSettings) -> BleakAirthingsReader:
    """Build the production reader with its scan bounded inside ``poll_timeout``.

    A quarter of the poll budget (at most :data:`SCAN_TIMEOUT_SECONDS`) leaves
    the rest for connecting and reading.
    """
    return BleakAirthingsReader(
        scan_timeout=min(SCAN_TIMEOUT_SECONDS, settings.poll_timeout / 4)
    )


app = cosalette.App(
    name="airthings2mqtt",
    version=__version__,
    settings_class=Airthings2MqttSettings,
    adapters={
        AirthingsReaderPort: (_make_reader, FakeAirthingsReader),
    },
    error_type_map=error_type_map,
    # bleak/BlueZ log records embed the full sensor MAC; scrub them like the
    # adapter already scrubs error text (cosalette ADR-085).
    redact=redact_macs_in,
    # Replaced by _configure_exit_after_stale once CLI settings load.
    exit_after_stale=Airthings2MqttSettings.model_fields["exit_after_stale"].default,
)

RETRY_ON = (BleConnectionError, BleTimeoutError, TimeoutError)
"""Transport failures worth retrying within one poll."""

UNAVAILABLE_ON = (*RETRY_ON, BleReadError)
"""Terminal poll failures that mark the sensor offline.

A persistent ``BleReadError`` (missing characteristic, undecodable frame) is
not retried, but it leaves consumers without a fresh reading all the same.
"""

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


_TRIGGER_MIN_INTERVAL_SECONDS: float = Airthings2MqttSettings.model_fields[
    "trigger_min_interval"
].default
"""Default spacing between trigger-initiated reads (cosalette ADR-066).

Sourced from the ``trigger_min_interval`` settings field default so the two
never drift. A BLE connect/read to the Airthings takes seconds and drains a
battery-powered sensor, and ``airthings2mqtt/airthings/set`` is a public MQTT
topic - a dashboard button held down, or an automation loop, would otherwise
queue one round-trip per message. A wake inside a closed window is *held*, not
dropped, so the re-read still happens; it just waits for the window to reopen.
Well under the default ``poll_interval`` so it never throttles the scheduled
cadence. Deployments override it via ``AIRTHINGS2MQTT_TRIGGER_MIN_INTERVAL``.
"""


def _configure_trigger_min_interval(settings: Airthings2MqttSettings) -> None:
    """Apply the final CLI-loaded throttle before cosalette builds trigger slots.

    The CLI resolves ``--env-file`` and ``--config-file`` settings after module
    import. ``on_configure`` runs with those settings before trigger slots are
    built, so update the frozen registration at that point.
    """
    for index, registration in enumerate(app._telemetry):
        if registration.func is _telemetry:
            app._telemetry[index] = replace(
                registration, min_interval=settings.trigger_min_interval
            )
            return
    raise RuntimeError("Airthings telemetry registration was not found")


app.on_configure(_configure_trigger_min_interval)


def _configure_exit_after_stale(settings: Airthings2MqttSettings) -> None:
    """Apply the CLI-loaded ``exit_after_stale`` before the watchdog starts.

    A stale sensor ends the app with exit code 5 and ``restart: unless-stopped``
    restarts it (monorepo ADR-010). ``0`` disables the exit. cosalette reads
    the value when it starts the freshness watchdog, after the ``on_configure``
    hooks.
    """
    app._exit_after_stale = settings.exit_after_stale or None


app.on_configure(_configure_exit_after_stale)

_STORE_KEY = "reset_tracker"
"""Device-store key holding the :class:`ResetState` (ADR-004)."""


@app.telemetry(
    lambda settings: [settings.device_name],
    interval=setting_ref("poll_interval"),
    timeout=setting_ref("poll_timeout"),
    triggerable=True,
    # Replaced by _configure_trigger_min_interval after CLI settings load and
    # before cosalette builds trigger slots.
    min_interval=_TRIGGER_MIN_INTERVAL_SECONDS,
    retry=3,
    retry_on=RETRY_ON,
    unavailable_on=UNAVAILABLE_ON,
    # stale_after stays derived (ADR-080): 2 x poll_interval + 4 x poll_timeout
    # + 3 x 72 s backoff = 3696 s (~62 min) with the defaults.
    summary="Read Airthings BLE sensor values (temperature, humidity, radon)",
    state_model=AirthingsReading,
    persist=SaveOnChange(),
)
async def _telemetry(
    reader: AirthingsReaderPort,
    settings: Airthings2MqttSettings,
    trigger: cosalette.TriggerPayload,
    logger: logging.Logger,
    store: DeviceStore,
) -> AirthingsReading:
    """Read all sensor values and return the reading.

    The reading passes through the reset tracker (ADR-004) first: radon
    placeholders after a battery change are withheld and the lifecycle fields
    are set. The tracker state lives in the device store, so a restart
    neither loses a reset nor reports it twice.
    """
    if trigger.is_triggered:
        logger.info("On-demand Airthings re-read triggered")

    async with _get_read_lock():
        raw = await reader.read(settings.device_mac)

    state = ResetState.from_dict(store.get(_STORE_KEY))
    reading, new_state, reset = track(
        raw, state, timedelta(days=settings.lta_settle_days)
    )
    if reset:
        logger.info(
            "Airthings sensor reset detected (battery change or power loss): "
            "long-term average %s -> %s; radon is withheld while the sensor "
            "reports 0/0",
            new_state.lta_before_reset,
            raw.radon_long_term_avg,
        )
    if new_state != state:
        store[_STORE_KEY] = new_state.to_dict()  # saved by persist=SaveOnChange()
    return reading


def main() -> None:
    """Start the application, or run a CLI subcommand such as ``schema``.

    ``cli()`` rather than ``run()``: it keeps the ``schema`` and ``health``
    subcommands and the cosalette flags (``--dry-run``, ``--env-file``,
    ``--version``). The image ships no HEALTHCHECK (monorepo ADR-010);
    ``health`` stays for operators who run their own probe with
    ``COSALETTE_HEALTH_FILE`` set.
    """
    app.cli()
