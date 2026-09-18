"""Integration tests for airthings2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract

from .conftest import DEVICE_NAME, TOPIC_PREFIX, _FastPollSettings, make_harness

STATE_TOPIC = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"


async def _observe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **mqtt: object
) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    # The discovery snapshot store would otherwise land in the user's state dir.
    monkeypatch.setenv("AIRTHINGS2MQTT_STORE_PATH", str(tmp_path / "store.json"))
    harness = make_harness(
        settings=_FastPollSettings(
            device_mac="AA:BB:CC:DD:EE:FF",
            poll_interval=3600,
            mqtt={"tls": False, **mqtt},
        )
    )
    harness.app.discovery()
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
async def mqtt5(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Observation:
    return await _observe(
        monkeypatch,
        tmp_path,
        protocol_version="5",
        message_expiry_interval=EXPIRY_SECONDS,
    )


@pytest.fixture
async def mqtt311(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Observation:
    return await _observe(monkeypatch, tmp_path, protocol_version="3.1.1")


@pytest.mark.integration
class TestMqtt5RetainedExpiry(Mqtt5Contract):
    state_topic = STATE_TOPIC


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
