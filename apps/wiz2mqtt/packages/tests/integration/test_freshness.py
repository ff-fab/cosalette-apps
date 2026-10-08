"""Integration tests for the per-bulb freshness policy.

With the production 60 s tick and 180 s tick timeout, cosalette derives
``stale_after`` for each bulb as ``2 x 60 + 180 = 300 s`` (ADR-080, ``retry=0``).
The freshness watchdog checks every 60 s.

A fresh cycle is a tick that returns, whatever it publishes. A bulb on a dark
``no_power`` circuit still completes every tick (it skips the read and reports
its desired state), so it never turns stale and stays ``online``. Only a tick
that fails outside the reachability debounce turns the bulb stale and offline.
wiz2mqtt sets neither ``exit_after_stale`` nor ``restart_on_stale``.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the derived bound
- Equivalence Partitioning: unreachable bulb on a dark circuit vs failing tick
- State Transition: ok -> error -> stale, with the app still running
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.main import _TICK_INTERVAL_SECONDS, _TICK_TIMEOUT_SECONDS
from wiz2mqtt.models import BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

from .conftest import TOPIC_PREFIX, build_integration_app, make_settings

_DERIVED_STALE_AFTER = int(2 * _TICK_INTERVAL_SECONDS + _TICK_TIMEOUT_SECONDS)
"""The derived per-bulb bound; see module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = (_DERIVED_STALE_AFTER // _CHECK_INTERVAL + 1) * _CHECK_INTERVAL
"""The first watchdog check past the derived bound."""

_STATUS_TOPIC = f"{TOPIC_PREFIX}/status"
_AVAILABILITY_TOPIC = f"{TOPIC_PREFIX}/office/availability"


class _BrokenTickAdapter(FakeWizBulbAdapter):
    """Fake adapter whose reads fail with a bug, not a bridge error."""

    broken = False

    async def get_state(self, ip: str) -> BulbState:
        if self.broken:
            msg = "unexpected adapter bug"
            raise RuntimeError(msg)
        return await super().get_state(ip)


def _office_status(harness: AppHarness) -> str:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    return json.loads(payload)["devices"]["office"]["status"]


def _availability(harness: AppHarness) -> str | None:
    messages = harness.messages_for(_AVAILABILITY_TOPIC)
    return messages[-1][0] if messages else None


async def _run(
    adapter: FakeWizBulbAdapter, settings: Wiz2MqttSettings, target: int
) -> tuple[AppHarness, asyncio.Task[None], list[str]]:
    """Run the app to *target* seconds; return the status at each check."""
    harness = AppHarness(
        app=build_integration_app(
            adapter,
            interval=_TICK_INTERVAL_SECONDS,
            timeout=_TICK_TIMEOUT_SECONDS,
        ),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=settings,
        shutdown_event=asyncio.Event(),
    )
    task = asyncio.create_task(harness.run())
    await harness.wait_for_publish_count(_STATUS_TOPIC, 1)
    statuses = []
    for _ in range(target // _CHECK_INTERVAL):
        await harness.advance_time(_CHECK_INTERVAL)
        statuses.append(_office_status(harness))
    return harness, task, statuses


async def _stop(harness: AppHarness, task: asyncio.Task[None]) -> None:
    harness.shutdown_event.set()
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.integration
async def test_bulb_on_dark_circuit_never_goes_stale() -> None:
    """An unreachable bulb behind a ``no_power`` source stays fresh and online.

    Technique: Equivalence Partitioning — the mains-off partition. Every tick
    skips or fails the read but still returns, so well past the derived bound
    the heartbeat reports ``ok`` at every check and availability stays ``online``.
    """
    adapter = FakeWizBulbAdapter()
    adapter.always_fail = True
    settings = make_settings(
        power_sources=[
            {
                "name": "office-power",
                "members": ["office"],
                "when_unreachable": "no_power",
            }
        ]
    )

    harness, task, statuses = await _run(adapter, settings, 2 * _STALE_AT)
    try:
        assert set(statuses) == {"ok"}
        assert _availability(harness) == "online"
        assert not task.done()
    finally:
        await _stop(harness, task)


@pytest.mark.integration
async def test_failing_tick_goes_stale_and_offline_without_exit() -> None:
    """A tick that keeps failing outside the debounce turns the bulb stale.

    Technique: Boundary Value Analysis — at the last check before 300 s the
    bulb is only ``error``; at the first check past it the heartbeat reports
    ``stale`` and the bulb goes ``offline``. The app keeps running.
    """
    adapter = _BrokenTickAdapter()
    adapter.broken = True

    harness, task, statuses = await _run(adapter, make_settings(), _STALE_AT)
    try:
        before = statuses[_DERIVED_STALE_AFTER // _CHECK_INTERVAL - 1]
        assert before == "error"
        assert statuses[-1] == "stale"
        assert _availability(harness) == "offline"
        assert not task.done()
    finally:
        await _stop(harness, task)
