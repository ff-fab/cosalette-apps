"""Integration tests for the retained power request of a power source (ADR-009).

Covers feature C end to end: a command for a bulb on a dark circuit reaches
``bulb_set``, latches a power-on request, and the source's own telemetry
entity publishes it retained on ``wiz2mqtt/{source}/state``. The idle timer
of the power-off direction takes an injected clock and is covered by the
unit tests in ``tests/unit/test_power.py``.

Test Techniques Used:
- Integration Testing: command dispatch and source publication through the
  real router, handler and telemetry entity
- Decision Table: the per-source opt-in decides whether a request appears
- Specification-based: the request is retained, and never a command topic
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.settings import Wiz2MqttSettings

from .conftest import (
    TOPIC_PREFIX,
    build_integration_app,
    make_settings,
    wait_until_subscribed,
)

SOURCE_NAME = "downstairs"
SOURCE_STATE_TOPIC = f"{TOPIC_PREFIX}/{SOURCE_NAME}/state"
BULB_STATE_TOPIC = f"{TOPIC_PREFIX}/office/state"


def _settings(*, enable_power_on_request: bool) -> Wiz2MqttSettings:
    """One bulb on a dark ``no_power`` circuit, with the opt-in under test."""
    return make_settings(
        power_sources=[
            {
                "name": SOURCE_NAME,
                "members": ["office"],
                "when_unreachable": "no_power",
                "enable_power_on_request": enable_power_on_request,
            }
        ]
    )


def _harness(
    fake_adapter: FakeWizBulbAdapter, *, enable_power_on_request: bool
) -> AppHarness:
    fake_adapter.always_fail = True
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=_settings(enable_power_on_request=enable_power_on_request),
        shutdown_event=asyncio.Event(),
    )


async def _run_with_commands(
    harness: AppHarness, *payloads: dict[str, object], expect_publishes: int
) -> None:
    """Start the app, deliver each command, then wait for the source publishes.

    The first publish is the startup tick, which always reports no request.
    Every command here reaches an unreachable bulb, so the bulb republishes
    its own desired state: that publish is the sentinel proving dispatch,
    even for a command that raises no request at all.
    """
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness)
        await harness.advance_time(0)
        await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 1)
        for payload in payloads:
            await harness.inject_command("office", payload)
        await harness.wait_for_publish_count(BULB_STATE_TOPIC, 1)
        await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, expect_publishes)
        await harness.clock.settle(stable_rounds=20)
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _requests(harness: AppHarness) -> list[object]:
    return [
        json.loads(payload)["power_request"]
        for payload, _retain, _qos in harness.messages_for(SOURCE_STATE_TOPIC)
    ]


@pytest.mark.integration
class TestPowerOnRequestPublication:
    """A command for a dark circuit publishes a retained power-on request."""

    async def test_command_publishes_the_request(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Integration — command to published request, end to end."""
        harness = _harness(fake_adapter, enable_power_on_request=True)

        await _run_with_commands(harness, {"state": "ON"}, expect_publishes=2)

        assert _requests(harness) == [None, "on"]

    async def test_the_request_is_retained(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — a consumer reads it on subscribe."""
        harness = _harness(fake_adapter, enable_power_on_request=True)

        await _run_with_commands(harness, {"state": "ON"}, expect_publishes=2)

        assert all(
            retain
            for _payload, retain, _qos in harness.messages_for(SOURCE_STATE_TOPIC)
        )

    async def test_two_identical_recomputations_produce_one_message(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — publish on change only.

        The second command repeats the first, so the recomputed payload is
        identical. The tick after it must add no message.
        """
        harness = _harness(fake_adapter, enable_power_on_request=True)

        await _run_with_commands(
            harness, {"state": "ON"}, {"state": "ON"}, expect_publishes=2
        )

        assert _requests(harness) == [None, "on"]

    async def test_off_command_promptly_clears_the_retained_request(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition — ON then OFF publishes the clear."""
        harness = _harness(fake_adapter, enable_power_on_request=True)
        task = asyncio.create_task(harness.run())
        try:
            await wait_until_subscribed(harness)
            await harness.advance_time(0)
            await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 1)

            await harness.inject_command("office", {"state": "ON"})
            await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 2)

            await harness.inject_command("office", {"state": "OFF"})
            await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 3)
            await harness.clock.settle(stable_rounds=20)
        finally:
            harness.shutdown_event.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert _requests(harness) == [None, "on", None]

    async def test_opt_out_publishes_no_request(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — the same command without the opt-in.

        The bulb's own state publish is the sentinel: it proves the command
        was dispatched while the source topic stayed at its startup message.
        """
        harness = _harness(fake_adapter, enable_power_on_request=False)

        await _run_with_commands(harness, {"state": "ON"}, expect_publishes=1)

        assert _requests(harness) == [None]
