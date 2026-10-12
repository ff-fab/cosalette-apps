"""Integration tests for the panel reachability probe (app ADR-001).

A ``ManualClock`` drives the fully wired app, so every probe cycle runs at an exact
virtual time and the 45 s sleep/wake bound is measured, not assumed.

Test Techniques Used:
- State Transition Testing: reachable -> unreachable -> reachable publishes
  display/state once per transition; pending -> confirmed / timeout
- Boundary Value Analysis: the transition lands by 35 s (interval 30 s plus the
  5 s debounce re-probe), inside the 45 s bound; the timeout not before 90 s
- Error Guessing: one lost probe does not flap; a command answer that lands
  during a probe wins; a restored "pending" is cleared
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

import pytest
from cosalette import MemoryStore, MockMqttClient, Store
from cosalette.testing import AppHarness, ManualClock

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol

from .conftest import (
    DISPLAY_SET,
    DISPLAY_STATE,
    SYSTEM_ACTION_SET,
    SYSTEM_ACTION_STATE,
    build_integration_app,
)

pytestmark = pytest.mark.integration


class Probe:
    """A running app under a ManualClock, with helpers that read the wire."""

    def __init__(self, harness: AppHarness, clock: ManualClock) -> None:
        self.harness = harness
        self.clock = clock

    def payloads(self, topic: str) -> list[dict[str, object]]:
        return [json.loads(p) for p, _, _ in self.harness.mqtt.get_messages_for(topic)]

    def available(self) -> list[object]:
        return [p["available"] for p in self.payloads(DISPLAY_STATE)]

    def observed(self) -> list[object]:
        return [p["observed"] for p in self.payloads(SYSTEM_ACTION_STATE)]

    async def advance(self, seconds: float) -> None:
        await asyncio.wait_for(self.harness.advance_time(seconds), 5.0)

    async def command(self, topic: str, payload: dict[str, object]) -> None:
        state_topic = topic.removesuffix("/set") + "/state"
        before = len(self.harness.mqtt.get_messages_for(state_topic))
        await self.harness.inject_command(None, payload, topic=topic)
        await asyncio.wait_for(
            self.harness.wait_for_publish_count(state_topic, before + 1), 5.0
        )
        await self.clock.settle()  # let a woken probe park on its sleep


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


async def _start(
    fake_wallpanel: FakeWallpanel, fake_wol: FakeWol, store: Store
) -> AsyncIterator[Probe]:
    clock = ManualClock()
    harness = AppHarness(
        app=build_integration_app(fake_wallpanel, fake_wol, store),
        mqtt=MockMqttClient(),
        clock=clock,
        settings=make_wallpanel_control_settings(),
        shutdown_event=asyncio.Event(),
    )
    task = asyncio.create_task(harness.run())
    try:
        await asyncio.wait_for(
            clock.settle(
                until=lambda: (
                    {DISPLAY_SET, SYSTEM_ACTION_SET} <= set(harness.mqtt.subscriptions)
                ),
                max_rounds=10_000,
            ),
            5.0,
        )
        # The first cycle publishes at once; after it the probe waits on the clock.
        await asyncio.wait_for(harness.wait_for_publish_count(DISPLAY_STATE, 1), 5.0)
        yield Probe(harness, clock)
    finally:
        harness.shutdown_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.fixture
async def probe(
    fake_wallpanel: FakeWallpanel, fake_wol: FakeWol, store: MemoryStore
) -> AsyncIterator[Probe]:
    """The app with the probe on; its first cycle saw a reachable panel at 0 s."""
    async for running in _start(fake_wallpanel, fake_wol, store):
        yield running


@pytest.fixture
async def asleep(
    fake_wallpanel: FakeWallpanel, fake_wol: FakeWol, store: MemoryStore
) -> AsyncIterator[Probe]:
    """The panel fell asleep at 0 s; the cycle that saw it ended at 35 s."""
    async for running in _start(fake_wallpanel, fake_wol, store):
        fake_wallpanel.set_reachable(False)
        await running.advance(35)
        yield running


class TestReachabilityTransitions:
    """display/state follows the panel within 45 s and only on a transition."""

    async def test_first_cycle_publishes_a_fresh_read(self, probe: Probe) -> None:
        assert probe.available() == [True]
        assert probe.payloads(DISPLAY_STATE)[0]["state"] is not None

    async def test_sleep_is_published_within_45_seconds(
        self, probe: Probe, fake_wallpanel: FakeWallpanel
    ) -> None:
        fake_wallpanel.set_reachable(False)

        await probe.advance(34)
        assert probe.available() == [True]
        await probe.advance(1)
        assert probe.available() == [True, False]

    async def test_wake_is_published_within_45_seconds(
        self, asleep: Probe, fake_wallpanel: FakeWallpanel
    ) -> None:
        assert asleep.available() == [True, False]
        fake_wallpanel.set_reachable(True)

        await asleep.advance(29)
        assert asleep.available() == [True, False]
        await asleep.advance(1)  # t = 65 s: the next cycle succeeds at once
        assert asleep.available() == [True, False, True]
        assert asleep.payloads(DISPLAY_STATE)[-1]["state"] is not None

    async def test_unchanged_reachability_publishes_nothing(self, probe: Probe) -> None:
        await probe.advance(300)

        assert probe.available() == [True]

    async def test_one_lost_probe_does_not_flap(
        self, probe: Probe, fake_wallpanel: FakeWallpanel
    ) -> None:
        fake_wallpanel.set_reachable(False)
        await probe.advance(30)  # first probe of the cycle fails
        fake_wallpanel.set_reachable(True)
        await probe.advance(5)  # the re-probe succeeds

        assert probe.available() == [True]

    async def test_a_command_answer_during_a_probe_wins(
        self, probe: Probe, fake_wallpanel: FakeWallpanel
    ) -> None:
        fake_wallpanel.set_reachable(False)
        await probe.advance(30)  # first probe fails; the re-probe is due at 35 s
        fake_wallpanel.set_reachable(True)
        await probe.command(DISPLAY_SET, {"state": "on"})
        fake_wallpanel.set_reachable(False)

        await probe.advance(5)  # the re-probe fails, but the command answered later
        assert probe.available() == [True, True]
        await probe.advance(35)  # the next cycle publishes the transition
        assert probe.available() == [True, True, False]


class TestActionConfirmation:
    """An accepted action answers "pending"; the probe resolves it."""

    async def test_wake_is_confirmed_when_the_panel_answers(
        self, asleep: Probe, fake_wallpanel: FakeWallpanel
    ) -> None:
        await asleep.command(SYSTEM_ACTION_SET, {"action": "wake"})
        fake_wallpanel.set_reachable(True)

        await asleep.advance(5)

        assert asleep.observed() == ["pending", "confirmed"]
        assert asleep.available() == [True, False, True]

    async def test_suspend_is_confirmed_when_the_panel_stops_answering(
        self, probe: Probe
    ) -> None:
        await probe.command(SYSTEM_ACTION_SET, {"action": "suspend"})

        await probe.advance(10)  # wake-up delay, then the debounce re-probe

        assert probe.observed() == ["pending", "confirmed"]
        assert probe.available() == [True, False]

    async def test_wake_times_out_with_a_warning(
        self,
        asleep: Probe,
        fake_wallpanel: FakeWallpanel,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        await asleep.command(SYSTEM_ACTION_SET, {"action": "wake"})
        caplog.set_level(logging.WARNING, logger="wallpanel_control.devices.probe")

        await asleep.advance(89)  # acceptance at t=35; deadline at t=125
        assert asleep.observed() == ["pending"]
        # A target observation arriving exactly at the deadline is still timed out.
        fake_wallpanel.set_reachable(True)
        await asleep.advance(1)

        assert asleep.observed() == ["pending", "timeout"]
        assert "WOL_BROADCAST" in caplog.text

    async def test_a_restored_pending_answer_is_cleared(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        store: MemoryStore,
    ) -> None:
        async for first in _start(fake_wallpanel, fake_wol, store):
            await first.command(SYSTEM_ACTION_SET, {"action": "wake"})
            assert first.observed() == ["pending"]  # stopped before it resolved

        async for second in _start(fake_wallpanel, fake_wol, store):
            assert second.observed() == [None]
