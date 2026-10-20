"""Integration tests for the dead-tube path: offline, never stale, never exit.

``radiation`` sets ``stale_after=None``: every NoPulseError is a failed cycle,
so with the derived freshness bound (2 x 30 + 30 = 90 s, ADR-080) a dead tube
would turn the channel stale. These tests pin that it does not, so the app
keeps running with the channel offline until pulses return.

Test Techniques Used:
- State Transition: online → offline (no pulse) → online (pulse resumes),
  with the app running throughout.
- Boundary Value Analysis: one run before and at the no-pulse timeout.
- Error Guessing: an hour without pulses never reports ``stale`` and never
  ends the run (the failure a derived freshness bound would cause).
"""

from __future__ import annotations

import json

import pytest
from cosalette.testing import AppHarness

from geiger2mqtt.adapters.fake import FakePulseCounter

from .conftest import (
    AVAILABILITY_TOPIC,
    STATE_TOPIC,
    STATUS_TOPIC,
    make_harness,
    running,
)

pytestmark = pytest.mark.integration


def _last(harness: AppHarness, topic: str) -> str:
    return harness.messages_for(topic)[-1][0]


def _radiation_status(harness: AppHarness) -> str:
    return json.loads(_last(harness, STATUS_TOPIC))["devices"]["radiation"]["status"]


async def test_dead_tube_goes_offline_and_recovers_without_exit() -> None:
    counters: list[FakePulseCounter] = []
    harness = make_harness(fake={"cpm": 0.0}, counters=counters, no_pulse_timeout=300)

    async with running(harness) as task:
        for _ in range(9):  # 270 s: zero readings, inside the timeout
            await harness.advance_time(30)
        assert _last(harness, AVAILABILITY_TOPIC) == "online"
        published = len(harness.messages_for(STATE_TOPIC))

        await harness.advance_time(30)  # 300 s: the timeout is reached
        assert _last(harness, AVAILABILITY_TOPIC) == "offline"

        for _ in range(120):  # one more hour without a pulse
            await harness.advance_time(30)
        assert not task.done()
        assert _radiation_status(harness) != "stale"
        assert len(harness.messages_for(STATE_TOPIC)) == published

        counters[-1].record()
        await harness.advance_time(30)
        assert _last(harness, AVAILABILITY_TOPIC) == "online"
        assert json.loads(_last(harness, STATE_TOPIC))["cpm"] == 1
