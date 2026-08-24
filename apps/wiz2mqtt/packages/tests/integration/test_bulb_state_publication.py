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
