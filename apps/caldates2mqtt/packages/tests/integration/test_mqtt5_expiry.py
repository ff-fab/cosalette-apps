"""Integration tests for caldates2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.
"""

from __future__ import annotations

import pytest

from caldates2mqtt.adapters.fake import FakeCalDavReader
from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract

from .conftest import TOPIC_PREFIX, _FastPollSettings, calendar_config, make_harness

STATE_TOPIC = f"{TOPIC_PREFIX}/garbage/state"

# The default test schedule fires every 3 s of virtual time and would republish
# the state topic on its own, hiding the refresh. This one fires once a year.
_YEARLY_CRON = "0 0 0 1 1 ?"


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    calendar = calendar_config("garbage").model_copy(update={"schedule": _YEARLY_CRON})
    harness = make_harness(
        FakeCalDavReader(),
        [calendar],
        settings=_FastPollSettings(calendars=[calendar], mqtt={"tls": False, **mqtt}),
    )
    broker = FakeMqtt5Broker(harness.clock)
    broker.install(monkeypatch)
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
