"""Integration helpers: the real app with a fake counter on the harness clock."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from geiger2mqtt.adapters.fake import FakePulseCounter
from geiger2mqtt.main import create_app
from geiger2mqtt.settings import Geiger2MqttSettings
from tests.fixtures.config import make_settings

STATE_TOPIC = "geiger2mqtt/radiation/state"
AVAILABILITY_TOPIC = "geiger2mqtt/radiation/availability"
STATUS_TOPIC = "geiger2mqtt/status"


def make_harness(
    *,
    fake: dict[str, Any] | None = None,
    counters: list[FakePulseCounter] | None = None,
    **overrides: Any,
) -> AppHarness:
    """Build ``create_app()`` with a seeded fake counter on the harness clock.

    *fake* holds extra FakePulseCounter arguments; each counter the app
    creates is appended to *counters*.
    """
    clock = ManualClock()
    created = [] if counters is None else counters

    def counter(settings: Geiger2MqttSettings) -> FakePulseCounter:
        created.append(
            FakePulseCounter(settings, clock=clock.now, **({"seed": 1} | (fake or {})))
        )
        return created[-1]

    overrides.setdefault("mqtt", {"tls": False})
    return AppHarness(
        app=create_app(pulse_counter=counter, dry_run_counter=counter),
        mqtt=MockMqttClient(),
        clock=clock,
        settings=make_settings(**overrides),
        shutdown_event=asyncio.Event(),
    )


@asynccontextmanager
async def running(harness: AppHarness) -> AsyncIterator[asyncio.Task[None]]:
    """Run the harness until the first heartbeat, then stop it on exit."""
    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(STATUS_TOPIC, 1)
        yield task
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
