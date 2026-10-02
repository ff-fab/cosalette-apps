"""Integration tests for the bulb_entity telemetry device .

Exercises the full state-publication path: FakeWizBulbAdapter ->
bulb_entity_tick -> the cosalette telemetry runner's OnChange() gating ->
in-memory test double port.

Test Techniques Used:
- Integration Testing: full telemetry dispatch through the cosalette framework
- Decision Table: when_unreachable "unavailable" vs. "off" branches
- State Transition Testing: offline -> online availability recovery
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import pytest
from cosalette import MockMqttClient, MqttNotConnectedError
from cosalette.testing import AppHarness, ManualClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.models import BulbState

from .conftest import (
    _FAST_TICK_INTERVAL,
    NO_TICK_INTERVAL,
    TOPIC_PREFIX,
    build_integration_app,
    make_settings,
    wait_until_subscribed,
)

_SOURCE_TOPIC = f"{TOPIC_PREFIX}/office-power/state"
_ERROR_SUFFIX = "/error"

_TICKS = 3
"""Scheduled ticks to fire past the startup run.

Four runs total clears the framework's three-consecutive-failure offline
debounce ; the dedup and single-publish assertions only need the
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


class ConnectableMockMqttClient(MockMqttClient):
    """MQTT double whose initial publish attempts fail until ``connect()``.

    The connect callbacks make this a real ``MqttConnectAware`` structural
    match, exercising the runner's deferred-telemetry wake rather than
    manually advancing its scheduled interval.
    """

    def __init__(self) -> None:
        super().__init__()
        self.attempted_topics: list[str] = []
        self._connected = False
        self._connect_callbacks: list[Callable[[], Awaitable[None]]] = []

    @property
    def is_connected(self) -> bool:
        """Expose the current transport state to cosalette's first-connect gate."""
        return self._connected

    def add_connect_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Register the callbacks that reannounce and wake deferred telemetry."""
        self._connect_callbacks.append(callback)

    async def publish(
        self,
        topic: str,
        payload: str | dict[str, object],
        *,
        retain: bool = False,
        qos: int = 1,
    ) -> None:
        """Record every attempted topic, rejecting sends before connection."""
        self.attempted_topics.append(topic)
        if not self._connected:
            raise MqttNotConnectedError("test MQTT client is disconnected")
        await super().publish(topic, payload, retain=retain, qos=qos)

    async def connect(self) -> None:
        """Connect and run the registered callbacks in production order."""
        self._connected = True
        for callback in self._connect_callbacks:
            await callback()


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
class TestPowerSourcePublication:
    """The source entity publishes a retained belief through its real registration.

    Technique: Integration Testing / Equivalence Partitioning — initial belief
    publication and repeated equal recomputations through ``OnChange``.
    """

    async def test_retained_source_payload_and_equal_beliefs_are_deduplicated(
        self, harness_when_off: AppHarness
    ) -> None:
        task = asyncio.create_task(harness_when_off.run())
        try:
            await wait_until_subscribed(harness_when_off)
            await harness_when_off.advance_time(0)
            await harness_when_off.wait_for_publish_count(_STATE_TOPIC, 1)
            await harness_when_off.clock.settle(stable_rounds=10)

            messages = harness_when_off.messages_for(_SOURCE_TOPIC)
            payload, retain, _qos = messages[-1]
            assert json.loads(payload) == {
                "powered": "on",
                "power_request": None,
                "members": ["office"],
            }
            assert retain is True

            published_count = len(messages)
            for _ in range(_TICKS):
                await harness_when_off.advance_time(_FAST_TICK_INTERVAL)
            await harness_when_off.clock.settle(stable_rounds=10)

            assert len(harness_when_off.messages_for(_SOURCE_TOPIC)) == published_count
        finally:
            harness_when_off.shutdown_event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task

    async def test_retries_initial_telemetry_after_mqtt_connect(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Initial telemetry before a broker connection is deferred, not failed.

        Technique: State Transition — disconnected → connected proves the
        deferred initial bulb telemetry wakes and arms its power source.

        Technique: Error Guessing — a transport exception at the state
        publish boundary must not be misclassified as a runner failure and
        emitted to either error topic.
        """
        mqtt = ConnectableMockMqttClient()
        harness = AppHarness(
            app=build_integration_app(
                fake_adapter,
                interval=NO_TICK_INTERVAL,
                startup_connect_timeout=None,
            ),
            mqtt=mqtt,
            clock=ManualClock(),
            settings=make_settings(
                power_sources=[{"name": "office-power", "members": ["office"]}]
            ),
            shutdown_event=asyncio.Event(),
        )
        task = asyncio.create_task(harness.run())
        try:
            await wait_until_subscribed(harness)
            await harness.clock.settle(stable_rounds=10)

            assert f"{TOPIC_PREFIX}/office/state" in mqtt.attempted_topics
            assert _SOURCE_TOPIC in mqtt.attempted_topics
            assert not any(
                topic.endswith(_ERROR_SUFFIX) for topic in mqtt.attempted_topics
            )

            await mqtt.connect()
            await harness.wait_for_publish_count(_SOURCE_TOPIC, 1)

            payload, retain, _qos = harness.messages_for(_SOURCE_TOPIC)[0]
            assert json.loads(payload)["powered"] == "on"
            assert retain is True
        finally:
            harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=2.0)


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
    """A bulb with when_unreachable='off' publishes its desired state while
    unreachable, never a hard-coded OFF (cap-bjw9.6), and never goes offline."""

    async def test_unreachable_bulb_with_no_prior_observation_publishes_nothing(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Boundary Value Analysis — unreachable from the very
        first tick, before any observation ever recorded a desired state.
        """
        fake_adapter.always_fail = True

        await _run_briefly(harness_when_off)

        assert harness_when_off.messages_for(f"{TOPIC_PREFIX}/office/state") == []

    async def test_unreachable_bulb_publishes_its_last_observed_state(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """cap-bjw9.6: once observed, the desired state republishes while
        unreachable — never a hard-coded OFF, replacing the pre-cap-bjw9.6
        behaviour this test used to pin.

        Technique: Decision Table — when_unreachable='off' failure branch,
        with a prior observation on record.
        """
        state_topic = f"{TOPIC_PREFIX}/office/state"
        observed_on = BulbState(
            state=True,
            brightness=222,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
        )
        task = asyncio.create_task(harness_when_off.run())
        try:
            await wait_until_subscribed(harness_when_off)
            await harness_when_off.advance_time(0)  # settle the startup run
            await harness_when_off.wait_for_publish_count(state_topic, 1)

            fake_adapter.inject_push("10.0.0.5", observed_on)
            await harness_when_off.wait_for_publish_count(state_topic, 2)

            fake_adapter.always_fail = True
            await harness_when_off.advance_time(_FAST_TICK_INTERVAL)
        finally:
            harness_when_off.shutdown_event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task

        payload, _retain, _qos = harness_when_off.messages_for(state_topic)[-1]
        body = json.loads(payload)
        # Not the fake adapter's OFF default, not a hard-coded guess — the
        # bulb's own last observation, carried through while unreachable.
        assert body["state"] == "ON"
        assert body["brightness"] == 222
        assert body["powered"] is True  # retained evidence clears at threshold

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
