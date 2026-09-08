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

from .conftest import _FAST_TICK_INTERVAL, TOPIC_PREFIX, wait_until_subscribed

_TICKS = 3
"""Scheduled ticks to fire past the startup run.

Four runs total clears the framework's three-consecutive-failure offline
debounce (cap-10u.13); the dedup and single-publish assertions only need the
run count above one. Each advance releases exactly one gated tick, so the
count is deterministic where the old real-sleep window was not.
"""


async def _run_briefly(harness: AppHarness) -> None:
    """Start the harness, fire a fixed number of telemetry ticks, then shut down.

    Under the gating ManualClock the startup run is settled onto its interval
    first, then each ``advance_time`` releases exactly one scheduled tick — a
    deterministic run count where the old real-sleep window admitted however
    many the loop happened to interleave.
    """
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness)
        await harness.advance_time(0)  # settle the startup run onto its interval
        for _ in range(_TICKS):
            await harness.advance_time(_FAST_TICK_INTERVAL)
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

        ``always_fail`` makes every run raise; the 4 runs from ``_TICKS=3``
        clear the 3-consecutive-failure offline debounce with one to spare.
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

_PUSHED_STATE = BulbState(
    state=True,
    brightness=42,
    hue=None,
    saturation=None,
    color_temp_kelvin=3000,
    scene=None,
)
"""A state that differs from the fake's default, so OnChange() lets it through."""


@pytest.mark.integration
class TestPushDrivenPublication:
    """A bulb push publishes immediately, without waiting for a scheduled tick.

    These run against ``push_harness``: ``interval=NO_TICK_INTERVAL`` (30 s)
    on a gating ``ManualClock``. Neither test advances that clock, so the
    scheduled tick cannot fire at all and only the startup run and a trigger
    wake can publish. A second message is therefore proof the
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
            await push_harness.wait_for_publish_count(_STATE_TOPIC, 1)  # startup run

            fake_adapter.inject_push(_BULB_IP, _PUSHED_STATE)
            await push_harness.wait_for_publish_count(_STATE_TOPIC, 2)

            payload, retain, _qos = push_harness.messages_for(_STATE_TOPIC)[1]
            assert json.loads(payload)["brightness"] == 42
            assert retain is True
        finally:
            push_harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)

    async def test_without_a_push_no_tick_can_publish(
        self, push_harness: AppHarness
    ) -> None:
        """The negative control for the test above.

        Technique: Specification-based — without it, a second publish could
        just be a tick and the trigger assertion would be vacuous. Generous
        ``stable_rounds``: ``settle()`` is a bounded heuristic and this reads
        an *absence*.
        """
        task = asyncio.create_task(push_harness.run())
        try:
            await wait_until_subscribed(push_harness)
            await push_harness.wait_for_publish_count(_STATE_TOPIC, 1)

            await push_harness.clock.settle(stable_rounds=20)

            assert len(push_harness.messages_for(_STATE_TOPIC)) == 1
        finally:
            push_harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)
