"""Integration tests for jeelink2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.

A sensor's state topic only exists after a frame, so the observation starts with
one frame from the office sensor and one ``mapping/state`` snapshot: the two
retained payloads jeelink2mqtt publishes beside the framework topics.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from jeelink2mqtt import receiver as _receiver
from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract

from .test_event_driven_acceptance import (
    _deliver,
    _receiver_context,
    _wait_until,
    build_integration_app,
    make_settings,
    state_topic,
)

MAPPING_TOPIC = "jeelink2mqtt/mapping/state"


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    captured: dict[str, Any] = {}
    app = build_integration_app(captured)
    app.discovery()
    settings = make_settings()
    settings.mqtt = settings.mqtt.model_copy(update={"tls": False, **mqtt})
    harness = AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=clock,
        settings=settings,
        shutdown_event=asyncio.Event(),
    )

    async def frame_and_mapping() -> None:
        await _wait_until(
            lambda: "notify" in captured and bool(captured["notify"].entities),
            "the framework to bind the sensor entities' trigger slots",
        )
        await _deliver(harness, captured)
        await _receiver.publish_mapping_state(
            _receiver_context(harness), captured["state"]
        )

    return await run_against_broker(
        harness,
        broker,
        ready_topic=state_topic(),
        windows=WINDOWS,
        window_seconds=EXPIRY_SECONDS / 3,
        prepare=frame_and_mapping,
    )


@pytest.fixture
async def mqtt5(monkeypatch: pytest.MonkeyPatch) -> Observation:
    return await _observe(
        monkeypatch, protocol_version="5", message_expiry_interval=EXPIRY_SECONDS
    )


@pytest.fixture
async def mqtt311(monkeypatch: pytest.MonkeyPatch) -> Observation:
    return await _observe(monkeypatch, protocol_version="3.1.1")


@pytest.mark.integration
class TestMqtt5RetainedExpiry(Mqtt5Contract):
    state_topic = state_topic()

    def test_mapping_snapshot_is_retained_with_the_expiry(
        self, mqtt5: Observation
    ) -> None:
        """Technique: Specification-based - an ad-hoc retained publish is stamped."""
        publishes = mqtt5.broker.publishes_to(MAPPING_TOPIC)

        assert publishes
        assert {p.retain for p in publishes} == {True}
        assert {p.expiry for p in publishes} == {EXPIRY_SECONDS}


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
