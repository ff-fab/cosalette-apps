"""Integration tests for gas2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from tests.fixtures.config import make_gas2mqtt_settings

from .conftest import build_full_integration_app

STATE_TOPIC = "gas2mqtt/gas_counter/state"


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    app = build_full_integration_app()
    app.discovery()
    harness = AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=clock,
        settings=make_gas2mqtt_settings(
            mqtt={"tls": False, **mqtt},
            poll_interval=3600,
            temperature_interval=3600,
        ),
        shutdown_event=asyncio.Event(),
    )
    return await run_against_broker(
        harness,
        broker,
        ready_topic=STATE_TOPIC,
        windows=WINDOWS,
        window_seconds=EXPIRY_SECONDS / 3,
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
    state_topic = STATE_TOPIC


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
