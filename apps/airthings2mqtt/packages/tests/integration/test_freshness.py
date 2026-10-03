"""Integration tests for the derived telemetry freshness bound (ADR-080).

With the shipped 25-minute poll, cosalette derives
``stale_after = 2 x 1500 + 120 x 4 + 72 x 3 = 3696 s`` from ``poll_interval``,
``poll_timeout``, ``retry=3`` and the default backoff. A sensor that stops
producing fresh readings must surface as ``"stale"`` in the status heartbeat
and as ``"offline"`` on availability once that window expires — even when the
failure is outside ``unavailable_on``.

Test Techniques Used:
- Boundary Value Analysis: just inside and just past the derived bound
- State Transition: ok -> error -> stale/offline on a ManualClock
"""

from __future__ import annotations

import asyncio
import json

import pytest

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.ports import AirthingsReading

from .conftest import DEVICE_NAME, TOPIC_PREFIX, _FastPollSettings, make_harness

_DERIVED_STALE_AFTER = 2 * 1500 + 120 * 4 + 72 * 3
"""The derived bound for the default settings; see the module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""


class _SucceedOnceReader(FakeAirthingsReader):
    """First read succeeds; every later read fails outside ``unavailable_on``."""

    async def read(self, mac: str) -> AirthingsReading:
        if self.calls:
            self.calls.append(mac)
            msg = "unexpected handler failure"
            raise RuntimeError(msg)
        return await super().read(mac)


def _device_status(payload: str) -> str:
    return json.loads(payload)["devices"][DEVICE_NAME]["status"]


@pytest.mark.integration
async def test_status_turns_stale_after_derived_bound_with_25_min_poll() -> None:
    """Heartbeat reports stale and availability offline once 3696 s pass.

    Technique: Boundary Value Analysis — one check before the bound the device
    is still only ``error``; one check past it, ``stale`` outranks ``error``
    and the freshness watchdog publishes ``"offline"``.
    """
    harness = make_harness(
        adapter=_SucceedOnceReader,
        settings=_FastPollSettings(device_mac="AA:BB:CC:DD:EE:FF", poll_interval=1500),
    )
    status_topic = f"{TOPIC_PREFIX}/status"
    availability_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability"
    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(f"{TOPIC_PREFIX}/{DEVICE_NAME}/state", 1)
        await harness.advance_time(0)
        elapsed = 0
        while elapsed < _DERIVED_STALE_AFTER - _CHECK_INTERVAL:
            await harness.advance_time(_CHECK_INTERVAL)
            elapsed += _CHECK_INTERVAL
        assert _device_status(harness.messages_for(status_topic)[-1][0]) == "error"
        assert harness.messages_for(availability_topic)[-1][0] == "online"

        for _ in range(2):
            await harness.advance_time(_CHECK_INTERVAL)
        assert _device_status(harness.messages_for(status_topic)[-1][0]) == "stale"
        assert harness.messages_for(availability_topic)[-1][0] == "offline"
    finally:
        harness.shutdown_event.set()
        await asyncio.wait_for(task, timeout=2.0)
