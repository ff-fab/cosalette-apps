"""Integration tests for the bulb_set command handler .

Exercises the full command path: MQTT inbound -> per-bulb command
dispatch -> BulbSetCommand mutual-exclusion validation ->
FakeWizBulbAdapter.set_state, using the real application wiring with an
in-memory test double port.

Test Techniques Used:
- Integration Testing: Full command dispatch through the cosalette framework
- Decision Table: valid partial updates vs. mutually-exclusive rejections
- Error Guessing: a conflicting payload is rejected and never reaches the adapter
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette.testing import AppHarness

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter

from .conftest import (
    _COMMAND_SETTLE_TIME,
    _FAST_TICK_INTERVAL,
    TOPIC_PREFIX,
    wait_until_subscribed,
)

_BULB_IP = "10.0.0.5"
_STATE_TOPIC = f"{TOPIC_PREFIX}/office/state"
_ERROR_TOPIC = f"{TOPIC_PREFIX}/office/error"


async def _run_with_command(
    harness: AppHarness,
    device: str,
    payload: dict,
) -> None:
    """Start the harness, deliver a command, then shut down cleanly."""
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness)
        await harness.inject_command(device, payload)
        await asyncio.sleep(_COMMAND_SETTLE_TIME)
        harness.shutdown_event.set()
        await task
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.integration
@pytest.mark.slow
class TestValidPartialUpdates:
    """Partial updates in both HA (multi-field) and openHAB (single-field) shapes."""

    async def test_multi_field_ha_style_payload_applies(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """A multi-field HA-style payload reaches the adapter as one update.

        Technique: Integration — verify command wiring through the full stack.
        """
        await _run_with_command(harness, "office", {"state": "ON", "brightness": 128})

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.state is True
        assert state.brightness == 128

    async def test_single_field_openhab_style_payload_applies(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """A single-field payload (openHAB's formatBeforePublish) applies.

        Technique: Equivalence Partitioning — single-field partial update.
        """
        await _run_with_command(harness, "office", {"brightness": 64})

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.brightness == 64

    async def test_color_payload_reaches_adapter_as_hue_saturation(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """A color-only payload is converted and applied, never as raw RGB.

        Technique: Integration — colour translation through the full stack.
        """
        await _run_with_command(
            harness, "office", {"color": {"r": 255, "g": 0, "b": 0}}
        )

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.hue is not None
        assert state.saturation is not None


@pytest.mark.integration
@pytest.mark.slow
class TestMutualExclusionRejection:
    """color, color_temp and effect conflicts are rejected before the adapter."""

    async def test_color_and_color_temp_together_is_rejected(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """color + color_temp is rejected and never reaches the adapter.

        Technique: Decision Table — mutually-exclusive combination.
        """
        await _run_with_command(
            harness,
            "office",
            {"color": {"r": 10, "g": 20, "b": 30}, "color_temp": 3000},
        )

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.hue is None
        assert state.color_temp_kelvin is None
        harness.assert_published(f"{TOPIC_PREFIX}/office/error")

    async def test_color_and_effect_together_is_rejected(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """color + effect is rejected and never reaches the adapter.

        Technique: Decision Table — mutually-exclusive combination.
        """
        await _run_with_command(
            harness,
            "office",
            {"color": {"r": 10, "g": 20, "b": 30}, "effect": 7},
        )

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.hue is None
        assert state.scene is None
        harness.assert_published(f"{TOPIC_PREFIX}/office/error")

    async def test_color_temp_and_effect_together_is_rejected(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """color_temp + effect is rejected and never reaches the adapter.

        Technique: Decision Table — mutually-exclusive combination.
        """
        await _run_with_command(harness, "office", {"color_temp": 3000, "effect": 7})

        state = await fake_adapter.get_state(_BULB_IP)
        assert state.color_temp_kelvin is None
        assert state.scene is None
        harness.assert_published(f"{TOPIC_PREFIX}/office/error")


@pytest.mark.integration
@pytest.mark.slow
class TestColourModeSupersession:
    """A colour-mode command clears the mode it supersedes in the published state.

    Regression coverage for cap-sxul: before the fix, the optimistic cache
    merge left a superseded mode's fields in place, so the second command's
    payload was byte-identical to the first and OnChange() published nothing
    at all — not a stale value, but no message.
    """

    async def test_color_after_color_temp_publishes_a_new_rgb_state(
        self, harness: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition Testing — CCT mode to RGB mode, end to end."""
        task = asyncio.create_task(harness.run())
        try:
            await wait_until_subscribed(harness)
            await harness.advance_time(0)  # settle the startup run
            await harness.wait_for_publish_count(_STATE_TOPIC, 1)

            await harness.inject_command("office", {"color_temp": 2700})
            await harness.advance_time(_FAST_TICK_INTERVAL)
            await harness.wait_for_publish_count(_STATE_TOPIC, 2)
            payload, _retain, _qos = harness.messages_for(_STATE_TOPIC)[1]
            assert json.loads(payload)["color_mode"] == "color_temp"

            await harness.inject_command(
                "office", {"color": {"r": 255, "g": 0, "b": 0}}
            )
            await harness.advance_time(_FAST_TICK_INTERVAL)
            await harness.wait_for_publish_count(_STATE_TOPIC, 3)
            payload, _retain, _qos = harness.messages_for(_STATE_TOPIC)[2]
            assert json.loads(payload)["color_mode"] == "rgb"
        finally:
            harness.shutdown_event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task


@pytest.mark.integration
@pytest.mark.slow
class TestQueueWhileUnreachable:
    """cap-bjw9.6 — a command to an unreachable bulb queues instead of erroring.

    ``harness_when_off``'s ``office`` bulb sits behind a ``no_power`` source
    (see ``conftest.settings_when_off``); setting the fake adapter
    unreachable before the harness starts keeps the source's belief at
    ``"off"`` for the whole run (no member ever answers, no signal exists).
    """

    async def test_command_to_unreachable_bulb_does_not_reach_the_wire(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — cap-bjw9.6 AC, no error, no wire call."""
        fake_adapter.set_unreachable(_BULB_IP, True)

        await _run_with_command(
            harness_when_off, "office", {"state": "ON", "brightness": 200}
        )

        assert fake_adapter.set_state_calls == []
        assert harness_when_off.messages_for(_ERROR_TOPIC) == []

    async def test_queued_command_republishes_the_desired_state(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Round-trip Testing — the queued intent reaches /state."""
        fake_adapter.set_unreachable(_BULB_IP, True)
        task = asyncio.create_task(harness_when_off.run())
        try:
            await wait_until_subscribed(harness_when_off)
            await harness_when_off.advance_time(0)  # settle the startup run

            await harness_when_off.inject_command(
                "office", {"state": "ON", "brightness": 200}
            )
            await asyncio.sleep(_COMMAND_SETTLE_TIME)  # let the command worker run
            await harness_when_off.wait_for_publish_count(_STATE_TOPIC, 1)
        finally:
            harness_when_off.shutdown_event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task

        payload, _retain, _qos = harness_when_off.messages_for(_STATE_TOPIC)[0]
        body = json.loads(payload)
        assert body["state"] == "ON"
        assert body["brightness"] == 200
        assert body["powered"] is False  # never a hard-coded OFF

    async def test_a_second_command_replaces_the_first_in_the_queue(
        self, harness_when_off: AppHarness, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition — the queue holds exactly one entry."""
        fake_adapter.set_unreachable(_BULB_IP, True)
        task = asyncio.create_task(harness_when_off.run())
        try:
            await wait_until_subscribed(harness_when_off)
            await harness_when_off.advance_time(0)

            await harness_when_off.inject_command("office", {"brightness": 50})
            await asyncio.sleep(_COMMAND_SETTLE_TIME)  # let the first command settle
            await harness_when_off.wait_for_publish_count(_STATE_TOPIC, 1)

            await harness_when_off.inject_command("office", {"brightness": 200})
            await asyncio.sleep(_COMMAND_SETTLE_TIME)  # let the second command run
            await harness_when_off.wait_for_publish_count(_STATE_TOPIC, 2)
        finally:
            harness_when_off.shutdown_event.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            else:
                await task

        # Only the newest command's value shows — nothing from the first.
        payload, _retain, _qos = harness_when_off.messages_for(_STATE_TOPIC)[-1]
        assert json.loads(payload)["brightness"] == 200
