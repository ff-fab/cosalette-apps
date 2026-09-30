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
- State Transition: the consumer contract — appearance-only commands, and
  release once the relay signal reports the circuit on
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


SIGNAL_TOPIC = "openhab/relay/downstairs/state"


async def _run_steps(
    harness: AppHarness,
    *steps: tuple[str, object, str, int],
) -> None:
    """Run the app through ``(kind, payload, topic, count)`` steps, then stop.

    ``kind`` is ``"command"`` (a bulb ``/set`` payload) or ``"signal"`` (a
    relay payload on :data:`SIGNAL_TOPIC`); each step then waits until
    *topic* has seen *count* publishes, which proves it was dispatched.
    """
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness, SIGNAL_TOPIC)
        await harness.advance_time(0)
        await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 1)
        for kind, payload, topic, count in steps:
            if kind == "command":
                await harness.inject_command("office", payload)
            else:
                await harness.mqtt.deliver(SIGNAL_TOPIC, str(payload))
            await harness.wait_for_publish_count(topic, count)
        await harness.clock.settle(stable_rounds=20)
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def _contract_harness(fake_adapter: FakeWizBulbAdapter) -> AppHarness:
    """A dark ``no_power`` circuit with the opt-in and a relay signal topic."""
    fake_adapter.always_fail = True
    settings = make_settings(
        power_sources=[
            {
                "name": SOURCE_NAME,
                "members": ["office"],
                "when_unreachable": "no_power",
                "enable_power_on_request": True,
                "signal_topic": SIGNAL_TOPIC,
            }
        ]
    )
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=settings,
        shutdown_event=asyncio.Event(),
    )


@pytest.mark.integration
class TestConsumerContract:
    """The contract ``docs/power-awareness.md`` promises a relay rule."""

    async def test_appearance_command_on_a_fresh_bulb_requests_power(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Equivalence Partitioning — no known intent reads as ON.

        A bulb with no recorded intent takes an effect-only command as a
        wish for light, so it raises the request like ``state: ON``.
        """
        harness = _harness(fake_adapter, enable_power_on_request=True)

        await _run_with_commands(harness, {"effect": "Party"}, expect_publishes=2)

        assert _requests(harness) == [None, "on"]

    async def test_appearance_command_on_a_bulb_meant_off_requests_nothing(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — appearance alone keeps an OFF intent.

        After ``state: OFF`` an effect-only command only restyles the bulb
        for later; the consumer must send ``state: ON`` to ask for power.
        """
        harness = _contract_harness(fake_adapter)

        await _run_steps(
            harness,
            ("command", {"state": "OFF"}, BULB_STATE_TOPIC, 1),
            ("command", {"effect": "Party"}, BULB_STATE_TOPIC, 2),
        )

        assert _requests(harness) == [None]

    async def test_relay_signal_on_releases_the_request(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: State Transition — request, relay reports on, release.

        The request is released on convergence, never on a timeout, so the
        consumer needs one rule on ``changed`` and no retry of its own.
        """
        harness = _contract_harness(fake_adapter)

        await _run_steps(
            harness,
            ("command", {"state": "ON"}, SOURCE_STATE_TOPIC, 2),
            ("signal", "on", SOURCE_STATE_TOPIC, 3),
        )

        assert _requests(harness) == [None, "on", None]
        assert harness.messages_for(SIGNAL_TOPIC) == []
