"""Integration tests for the bulb_entity telemetry device (cap-10u.13).

Exercises the full state-publication path: FakeWizBulbAdapter ->
bulb_entity_tick -> the cosalette telemetry runner's OnChange() gating ->
retained MQTT publish, using the real application wiring with an
in-memory test double port.

Test Techniques Used:
- Integration Testing: full telemetry dispatch through the cosalette framework
- Decision Table: when_unreachable "unavailable" vs. "off" branches
- State Transition Testing: offline -> online availability recovery
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette.testing import AppHarness

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.models import BulbState

from .conftest import TOPIC_PREFIX, wait_until_subscribed

_SETTLE_TIME = 0.05
"""Real seconds to let several fast (FakeClock) telemetry ticks run."""


async def _run_briefly(harness: AppHarness) -> None:
    """Start the harness, let some telemetry ticks fire, then shut down."""
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness)
        await asyncio.sleep(_SETTLE_TIME)
        harness.shutdown_event.set()
        await asyncio.wait_for(task, timeout=2.0)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.integration
@pytest.mark.slow
class TestStatePublication:
    """A reachable bulb publishes retained state and comes online."""

    async def test_publishes_retained_state(self, harness: AppHarness) -> None:
        """Technique: Integration — verify telemetry wiring through the full stack."""
        await _run_briefly(harness)

        harness.assert_published(f"{TOPIC_PREFIX}/office/state")
        payload, retain, _qos = harness.messages_for(f"{TOPIC_PREFIX}/office/state")[0]
        assert json.loads(payload)["state"] == "OFF"
        assert retain is True

    async def test_marks_bulb_available(self, harness: AppHarness) -> None:
        """Technique: Specification-based — recovery/first-contact signalling."""
        await _run_briefly(harness)

        harness.assert_published(
            f"{TOPIC_PREFIX}/office/availability", contains="online"
        )

    async def test_unchanged_state_is_not_republished(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """OnChange() dedups identical payloads across ticks.

        Technique: Equivalence Partitioning — the fake adapter's state never
        changes across ticks, so only the first tick should publish.
        """
        await _run_briefly(harness)

        assert fake_adapter.get_state_call_count >= 2, (
            "too few ticks — dedup assertion would be vacuous"
        )
        assert len(harness.messages_for(f"{TOPIC_PREFIX}/office/state")) == 1


@pytest.mark.integration
@pytest.mark.slow
class TestUnreachableBulb:
    """A bulb that never responds goes offline after repeated failures."""

    async def test_unreachable_bulb_goes_offline(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — when_unreachable='unavailable' (default).

        ``always_fail`` makes every get_state call raise, guaranteeing
        at least 3 consecutive failures regardless of tick count.
        """
        fake_adapter.always_fail = True

        await _run_briefly(harness)

        harness.assert_published(
            f"{TOPIC_PREFIX}/office/availability", contains="offline"
        )


@pytest.mark.integration
@pytest.mark.slow
class TestUnreachableBulbOffPolicy:
    """A bulb with when_unreachable='off' publishes OFF state, never goes offline."""

    async def test_unreachable_bulb_off_policy_publishes_off_state(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — when_unreachable='off' end-to-end wiring."""
        fake_adapter.always_fail = True

        await _run_briefly(harness_when_off)

        harness_when_off.assert_published(f"{TOPIC_PREFIX}/office/state")
        payload, _retain, _qos = harness_when_off.messages_for(
            f"{TOPIC_PREFIX}/office/state"
        )[0]
        assert json.loads(payload)["state"] == "OFF"

    async def test_unreachable_bulb_off_policy_marks_available(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — when_unreachable='off' never marks
        unavailable."""
        fake_adapter.always_fail = True

        await _run_briefly(harness_when_off)

        harness_when_off.assert_published(
            f"{TOPIC_PREFIX}/office/availability", contains="online"
        )


_BULB_IP = "10.0.0.5"
"""IP of the single bulb the ``test_settings`` fixture configures."""

_STATE_TOPIC = f"{TOPIC_PREFIX}/office/state"

_PUSH_WINDOW = 1.0
"""Seconds to wait for a push-driven publish before calling it a failure."""

_QUIET_WINDOW = 0.2
"""Seconds of deliberate inactivity used to prove no tick is due."""

_PUSHED_STATE = BulbState(
    state=True,
    brightness=42,
    hue=None,
    saturation=None,
    color_temp_kelvin=3000,
    scene=None,
)
"""A state that differs from the fake's default, so OnChange() lets it through."""


async def _wait_for_messages(harness: AppHarness, topic: str, count: int) -> None:
    """Poll until *topic* has at least *count* messages, or fail with the count."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _PUSH_WINDOW
    while len(harness.messages_for(topic)) < count:
        if loop.time() >= deadline:
            raise AssertionError(
                f"{topic} had {len(harness.messages_for(topic))} message(s), "
                f"expected {count}, after {_PUSH_WINDOW}s"
            )
        await asyncio.sleep(0.005)


@pytest.mark.integration
@pytest.mark.slow
class TestPushDrivenPublication:
    """A bulb push publishes immediately, without waiting for a scheduled tick.

    These run against ``push_harness``: ``interval=NO_TICK_INTERVAL`` (30 s)
    on a clock that really sleeps. Only the startup run and a trigger wake
    can publish inside the test window, so a second message is proof the
    ``triggerable="local"`` path works end to end — registration, adapter
    injection, ``EntityNotifier`` name resolution and the runner's trigger
    race all included.
    """

    async def test_push_publishes_before_the_next_scheduled_tick(
        self, push_harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Integration — the whole push→publish path in one assertion."""
        task = asyncio.create_task(push_harness.run())
        try:
            await wait_until_subscribed(push_harness)
            await _wait_for_messages(push_harness, _STATE_TOPIC, 1)  # startup run

            fake_adapter.inject_push(_BULB_IP, _PUSHED_STATE)
            await _wait_for_messages(push_harness, _STATE_TOPIC, 2)

            payload, retain, _qos = push_harness.messages_for(_STATE_TOPIC)[1]
            assert json.loads(payload)["brightness"] == 42
            assert retain is True
        finally:
            push_harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)

    async def test_without_a_push_the_long_interval_really_holds(
        self, push_harness: AppHarness
    ) -> None:
        """The negative control for the test above.

        Technique: Specification-based — without it, a second publish could
        just be a fast tick and the trigger assertion would be vacuous.
        """
        task = asyncio.create_task(push_harness.run())
        try:
            await wait_until_subscribed(push_harness)
            await _wait_for_messages(push_harness, _STATE_TOPIC, 1)

            await asyncio.sleep(_QUIET_WINDOW)

            assert len(push_harness.messages_for(_STATE_TOPIC)) == 1
        finally:
            push_harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)
