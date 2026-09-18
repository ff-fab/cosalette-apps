# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Integration tests for vito2mqtt's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the wired app against an in-memory broker
double; the shared contract assertions live in ``mqtt5_contract``. See there for
the test techniques used.

The polling intervals stay at their defaults (300 s and more): the observation
spans a few virtual seconds, so any repeat of a state topic comes from the
refresh ledger and not from a poll.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings

from .conftest import build_integration_app

STATE_TOPIC = "vito2mqtt/outdoor/state"


async def _observe(monkeypatch: pytest.MonkeyPatch, **mqtt: object) -> Observation:
    """Run the wired app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    app = build_integration_app(FakeOptolinkAdapter())
    app.discovery()  # ``main`` enables runtime Home Assistant discovery (ADR-004)
    harness = AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=clock,
        settings=Vito2MqttSettings(
            serial_port="/dev/ttyUSB0", mqtt={"tls": False, **mqtt}
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
