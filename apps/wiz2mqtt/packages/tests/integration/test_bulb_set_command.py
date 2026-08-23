"""Integration tests for the bulb_set command handler (cap-10u.12).

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

import pytest
from cosalette.testing import AppHarness

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter

from .conftest import _COMMAND_SETTLE_TIME, TOPIC_PREFIX, wait_until_subscribed

_BULB_IP = "10.0.0.5"


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
