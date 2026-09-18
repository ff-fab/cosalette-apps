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

"""Integration tests for suncast's MQTT 5 retained-message expiry (ADR-009).

The real cosalette ``MqttClient`` runs the real suncast app against an in-memory
broker double; the shared contract assertions live in ``mqtt5_contract``. See
there for the test techniques used.

suncast has no Home Assistant entity, so it publishes no discovery topic. Its
one payload topic is the retained SVG, which is the largest retained message any
app in the repository refreshes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from mqtt5_broker import FakeMqtt5Broker, Observation, run_against_broker
from mqtt5_contract import EXPIRY_SECONDS, WINDOWS, Mqtt5Contract, Mqtt311Contract
from suncast.app import app
from suncast.settings import SuncastSettings

STATE_TOPIC = "suncast/shadow/svg"
_LEDGER_BYTES = 16 * 1024 * 1024
_GEOMETRY = Path(__file__).parents[3] / "geometry.example.yaml"


async def _observe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **mqtt: object
) -> Observation:
    """Run the app for ``WINDOWS`` refresh windows against the broker double."""
    clock = ManualClock()
    broker = FakeMqtt5Broker(clock)
    broker.install(monkeypatch)
    harness = AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=clock,
        settings=SuncastSettings(
            latitude=47.3769,
            longitude=8.5417,
            timezone="Europe/Zurich",
            geometry_file=_GEOMETRY,
            output_path=tmp_path,
            mqtt={"tls": False, **mqtt},
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
    has_discovery = False

    def test_svg_stays_within_the_ledger_size_limit(self, mqtt5: Observation) -> None:
        """Technique: Boundary Value Analysis - the ledger holds at most 16 MiB.

        A retained publish that would push the refresh ledger past that limit
        raises, and suncast logs the failure and drops the SVG, so the payload
        that dominates the ledger must stay far below it.
        """
        svg = mqtt5.broker.retained[STATE_TOPIC].payload

        assert len(svg.encode()) < _LEDGER_BYTES // 16


@pytest.mark.integration
class TestMqtt311Default(Mqtt311Contract):
    pass
