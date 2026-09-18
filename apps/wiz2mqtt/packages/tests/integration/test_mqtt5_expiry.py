"""Integration tests for wiz2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.

The observation covers one bulb and one power source, so both kinds of retained
state topic are checked. The scheduled tick is far longer than the observation, so
any repeat of a state topic comes from the refresh ledger and not from a tick.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.discovery import make_discovery_enrich

from .conftest import (
    NO_TICK_INTERVAL,
    TOPIC_PREFIX,
    build_integration_app,
    make_settings,
)

STATE_TOPIC = f"{TOPIC_PREFIX}/office/state"
SOURCE_TOPIC = f"{TOPIC_PREFIX}/office-power/state"


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    app = build_integration_app(FakeWizBulbAdapter(), interval=NO_TICK_INTERVAL)
    app.discovery(enrich=make_discovery_enrich(app))
    settings = make_settings(
        power_sources=[
            {
                "name": "office-power",
                "members": ["office"],
                "when_unreachable": "no_power",
            }
        ]
    )
    settings.mqtt = settings.mqtt.model_copy(update={"tls": False, **mqtt})
    harness = AppHarness(
        app=app,
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

    def test_power_source_belief_is_refreshed_with_its_payload(
        self, mqtt5: Observation
    ) -> None:
        """Technique: Error Guessing - the refresh replays the belief unchanged."""
        publishes = mqtt5.broker.publishes_to(SOURCE_TOPIC)

        assert len(publishes) == mqtt5.startup_counts[SOURCE_TOPIC] + WINDOWS
        assert len({p.payload for p in publishes}) == 1


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
