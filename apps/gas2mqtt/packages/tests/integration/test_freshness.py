"""Integration tests for the telemetry freshness and stale exit policy.

With the default 1 s poll, cosalette derives ``stale_after`` for ``gas_counter``
as ``2 x 1 + 1 x 4 + 60 x 3 = 186 s`` (ADR-080: the implicit timeout equals the
interval and the backoff allowance has a 60 s floor). The freshness watchdog
checks every 60 s, so a sensor that stops answering at t=0 turns ``"stale"``
at the 240 s check, and ``exit_after_stale`` stops the app with code 5 at the
first check ``EXIT_AFTER_STALE`` seconds after that.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the derived bound and
  the exit_after_stale backstop
- State Transition: ok -> error -> stale -> exit
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette import MockMqttClient, StaleTelemetryError
from cosalette.testing import AppHarness, ManualClock

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.main import EXIT_AFTER_STALE
from tests.fixtures.config import make_gas2mqtt_settings

from .conftest import build_full_integration_app

_DERIVED_STALE_AFTER = 2 * 1 + 1 * 4 + 60 * 3
"""The derived gas_counter bound for the default settings; see module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = 240
"""The first check past the derived bound."""

_STATUS_TOPIC = "gas2mqtt/status"


def _gas_counter_status(harness: AppHarness) -> str:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    return json.loads(payload)["devices"]["gas_counter"]["status"]


@pytest.mark.integration
async def test_dead_sensor_goes_stale_then_exits_for_restart() -> None:
    """A sensor that stops answering turns stale, then the app exits 5.

    Technique: Boundary Value Analysis — at the check before 186 s the counter
    is only ``error``; the heartbeat after the 240 s check reports ``stale``.
    One check before ``_STALE_AT + EXIT_AFTER_STALE`` the app still runs; one
    check later the run ends with ``StaleTelemetryError`` (CLI exit code 5).
    """
    adapter = FakeMagnetometer()
    harness = AppHarness(
        app=build_full_integration_app(lambda: adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=make_gas2mqtt_settings(temperature_interval=3600),
        shutdown_event=asyncio.Event(),
    )
    elapsed = 0

    async def advance_to(target: int) -> None:
        # One poll interval at a time, so every poll and retry runs.
        nonlocal elapsed
        while elapsed < target:
            await harness.advance_time(1)
            elapsed += 1

    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(_STATUS_TOPIC, 1)
        await harness.advance_time(0)
        adapter.error_on_read = OSError("I2C bus gone")

        await advance_to(_DERIVED_STALE_AFTER - _CHECK_INTERVAL)
        assert _gas_counter_status(harness) == "error"

        await advance_to(_STALE_AT + _CHECK_INTERVAL)
        assert _gas_counter_status(harness) == "stale"

        await advance_to(_STALE_AT + int(EXIT_AFTER_STALE) - _CHECK_INTERVAL)
        assert not task.done()

        await advance_to(_STALE_AT + int(EXIT_AFTER_STALE) + _CHECK_INTERVAL)
        with pytest.raises(StaleTelemetryError):
            await asyncio.wait_for(task, timeout=2.0)
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
