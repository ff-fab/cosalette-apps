"""Integration tests for velux2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.

Startup homing is off: it presses the blind buttons on a real-time schedule that
the manual clock would hold back, and it has no bearing on the retained topics.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.devices.cover import CoverState, cover_device
from velux2mqtt.main import _cover_map
from velux2mqtt.ports import GpioSwitchPort
from velux2mqtt.settings import Velux2MqttSettings

from .conftest import TWO_COVERS

STATE_TOPIC = "velux2mqtt/blind/state"


def _build_app() -> App:
    """Mirror ``velux2mqtt.main``: the state model drives Home Assistant discovery."""
    app = App(
        name="velux2mqtt",
        version="0.0.0",
        settings_class=Velux2MqttSettings,
        adapters={GpioSwitchPort: FakeGpio},
    )
    app.discovery()
    app.device(name=_cover_map, state_model=CoverState)(cover_device)
    return app


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    settings = Velux2MqttSettings(
        covers=TWO_COVERS,
        enable_startup_homing=False,
        mqtt={"tls": False, **mqtt},
    )
    harness = AppHarness(
        app=_build_app(),
        mqtt=MockMqttClient(),
        clock=clock,
        settings=settings,
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
