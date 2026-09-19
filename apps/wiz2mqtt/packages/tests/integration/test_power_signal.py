"""Integration tests for the power source ``signal_topic`` inbound subscription.

Covers ADR-007's signal contract end to end: the relay signal arrives through
cosalette's ``@app.inbound()`` channel, feeds the belief, and is never
republished or announced to a consumer.

Test Techniques Used:
- Integration Testing: inbound delivery through the real router and handler
- Decision Table: signal x bulb evidence -> belief (ADR-007 rules 1 and 2)
- Error Guessing: payloads the contract rejects leave the belief unchanged
- Specification-based: the AsyncAPI document and the broker ACL carry the
  receive channel, and no discovery entity exists for it
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.models import BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

from .conftest import (
    TOPIC_PREFIX,
    build_integration_app,
    make_settings,
    wait_until_subscribed,
)

SIGNAL_TOPIC = "openhab/relay/downstairs/state"
SOURCE_STATE_TOPIC = f"{TOPIC_PREFIX}/downstairs/state"
BULB_STATE_TOPIC = f"{TOPIC_PREFIX}/office/state"
_TICKS_AFTER_THE_SIGNAL = 3
_TICK = 0.01


def _settings() -> Wiz2MqttSettings:
    return make_settings(
        power_sources=[
            {"name": "downstairs", "members": ["office"], "signal_topic": SIGNAL_TOPIC}
        ]
    )


def _harness(fake_adapter: FakeWizBulbAdapter) -> AppHarness:
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=_settings(),
        shutdown_event=asyncio.Event(),
    )


async def _run_with_signals(
    harness: AppHarness, *payloads: str, expect_source_publishes: int = 1
) -> None:
    """Start the app, deliver each payload to the signal topic, then stop.

    The router must hold the signal subscription before a payload goes out.
    A test that expects no belief change ends its payloads with a valid
    sentinel, and waits for the publish that the sentinel causes. The wait
    then proves the earlier payloads were dispatched.
    """
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness, SIGNAL_TOPIC)
        await harness.advance_time(0)  # settle the startup run
        await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 1)
        for payload in payloads:
            await harness.mqtt.deliver(SIGNAL_TOPIC, payload)
        if expect_source_publishes > 1:
            await harness.wait_for_publish_count(
                SOURCE_STATE_TOPIC, expect_source_publishes
            )
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _signal_off_after_an_answer(
    harness: AppHarness,
    fake_adapter: FakeWizBulbAdapter,
    *,
    bulb_keeps_answering: bool,
    expect_source_publishes: int,
) -> int:
    """Deliver ``off`` after the bulb answered, with no heartbeat tick after it.

    The signal arms the source and its bulb at once (ADR-007 amendment
    2026-09-19), so the clock stays still until the expected publishes
    arrive: each of them comes from the signal, not from a scheduled read.
    Return the count of reads in the heartbeat ticks after that.
    """
    fake_adapter.inject_push(
        "10.0.0.5",
        BulbState(
            state=True,
            brightness=100,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
        ),
    )
    task = asyncio.create_task(harness.run())
    try:
        await wait_until_subscribed(harness, SIGNAL_TOPIC)
        await harness.advance_time(0)
        await harness.wait_for_publish_count(SOURCE_STATE_TOPIC, 1)
        fake_adapter.always_fail = not bulb_keeps_answering
        await harness.mqtt.deliver(SIGNAL_TOPIC, "off")
        await harness.wait_for_publish_count(
            SOURCE_STATE_TOPIC, expect_source_publishes
        )
        reads = fake_adapter.get_state_call_count
        for _ in range(_TICKS_AFTER_THE_SIGNAL):
            await harness.advance_time(_TICK)
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    return fake_adapter.get_state_call_count - reads


def _powered_values(
    harness: AppHarness, topic: str = SOURCE_STATE_TOPIC
) -> list[object]:
    return [
        json.loads(payload)["powered"]
        for payload, _retain, _qos in harness.messages_for(topic)
    ]


@pytest.mark.integration
class TestPowerSignalInbound:
    """The relay signal feeds the belief of its source."""

    async def test_subscribes_to_the_signal_topic(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — the topic is a router subscription."""
        harness = _harness(fake_adapter)
        await _run_with_signals(harness)

        harness.assert_subscribed(SIGNAL_TOPIC)

    async def test_off_signal_sets_the_belief_when_no_bulb_answers(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — rule 2, no evidence and a signal.

        The bulb never answers, so before the signal the belief is ``unknown``
        (a ``fault`` source). The signal then decides.
        """
        fake_adapter.always_fail = True
        harness = _harness(fake_adapter)

        await _run_with_signals(harness, "off", expect_source_publishes=2)

        assert _powered_values(harness) == ["unknown", "off"]

    async def test_signal_is_trimmed_once(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Boundary Value Analysis — surrounding whitespace is accepted."""
        fake_adapter.always_fail = True
        harness = _harness(fake_adapter)

        await _run_with_signals(harness, "  on\n", expect_source_publishes=2)

        assert _powered_values(harness) == ["unknown", "on"]

    async def test_off_signal_newer_than_the_last_answer_decides_at_once(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — rule 2 over a stale answer (cap-hfro).

        The bulb answered before the signal and fails the one read that the
        signal arms. The belief goes ``off`` with no heartbeat tick, and the
        failed read is firm, so the later ticks skip the read.
        """
        harness = _harness(fake_adapter)

        reads = await _signal_off_after_an_answer(
            harness, fake_adapter, bulb_keeps_answering=False, expect_source_publishes=2
        )

        assert _powered_values(harness) == ["on", "off"]
        assert reads == 0

    async def test_answer_after_an_off_signal_outranks_it(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Decision Table — rule 1, newer evidence outranks the signal."""
        harness = _harness(fake_adapter)

        await _signal_off_after_an_answer(
            harness, fake_adapter, bulb_keeps_answering=True, expect_source_publishes=3
        )

        assert _powered_values(harness) == ["on", "off", "on"]

    @pytest.mark.parametrize("payload", ["ON", "true", "1", "", '{"state": "on"}'])
    async def test_invalid_payload_leaves_the_belief_unchanged(
        self, fake_adapter: FakeWizBulbAdapter, payload: str
    ) -> None:
        """Technique: Error Guessing — only lowercase on/off is a signal.

        The valid ``off`` after the invalid payload is the sentinel. A belief
        that goes ``unknown`` to ``off`` with no step between shows the invalid
        payload was dispatched and ignored.
        """
        fake_adapter.always_fail = True
        harness = _harness(fake_adapter)

        await _run_with_signals(harness, payload, "off", expect_source_publishes=2)

        assert _powered_values(harness) == ["unknown", "off"]

    async def test_signal_reaches_the_member_bulb_payload(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — the signal also decides the bulb payload."""
        harness = _harness(fake_adapter)

        await _signal_off_after_an_answer(
            harness, fake_adapter, bulb_keeps_answering=False, expect_source_publishes=2
        )

        assert _powered_values(harness, BULB_STATE_TOPIC) == [True, False]

    async def test_never_publishes_to_the_signal_topic(
        self, fake_adapter: FakeWizBulbAdapter
    ) -> None:
        """Technique: Specification-based — a status input, never republished."""
        fake_adapter.always_fail = True
        harness = _harness(fake_adapter)

        await _run_with_signals(harness, "off", expect_source_publishes=2)

        assert harness.messages_for(SIGNAL_TOPIC) == []
        assert not any("relay" in topic for topic, *_ in harness.published())


_PROFILE = """\
[[bulbs]]
name = "example"
ip = "192.0.2.1"

[[power_sources]]
name = "example-power"
members = ["example"]
signal_topic = "example/relay/state"
"""

_INHERITED_ENV_VARS = ("PATH", "PYTHONPATH", "HOME", "VIRTUAL_ENV")


def _cosalette(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", *args],
        capture_output=True,
        text=True,
        check=False,
        env={k: os.environ[k] for k in _INHERITED_ENV_VARS if k in os.environ},
    )
    assert result.returncode == 0, f"cosalette {args} exited:\n{result.stderr}"
    return result.stdout


@pytest.mark.integration
class TestPowerSignalContract:
    """The AsyncAPI document and the broker ACL carry the receive channel."""

    @pytest.fixture(scope="class")
    def schema_path(self, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Dump the schema resolved against a profile with one signal topic."""
        directory = tmp_path_factory.mktemp("power-signal-schema")
        profile = directory / "profile.toml"
        profile.write_text(_PROFILE)
        schema = directory / "schema.yaml"
        schema.write_text(
            _cosalette(
                "schema",
                "dump",
                "--app",
                "wiz2mqtt.main:app",
                "--resolve-settings",
                "--config-file",
                str(profile),
            )
        )
        return schema

    def test_asyncapi_has_a_receive_channel_for_the_signal_topic(
        self, schema_path: Path
    ) -> None:
        """Technique: Specification-based — an inbound receive channel exists."""
        text = schema_path.read_text()

        assert "address: example/relay/state" in text
        assert "x-cosalette-archetype: inbound" in text
        assert "receiveExample-powerInbound" in text

    def test_acl_lets_the_app_read_the_signal_topic(self, schema_path: Path) -> None:
        """Technique: Specification-based — subscribe permission, no write."""
        acl = _cosalette("schema", "acl", str(schema_path))

        assert "topic read example/relay/state" in acl
        assert "write example/relay/state" not in acl

    def test_no_discovery_entity_is_emitted_for_the_signal_topic(
        self, schema_path: Path
    ) -> None:
        """Technique: Specification-based — receive channels are not entities."""
        discovery = _cosalette("schema", "ha-discovery", str(schema_path))

        assert "relay" not in discovery
