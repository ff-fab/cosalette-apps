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

"""Integration test fixtures.

Provides a fully-wired App instance backed by in-memory test doubles
(FakeOptolinkAdapter, MockMqttClient, MemoryStore) so integration tests
can drive the real application logic without real I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MemoryStore, MockMqttClient

from vito2mqtt._version import __version__
from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices.commands import register_commands
from vito2mqtt.devices.legionella import register_legionella
from vito2mqtt.devices.telemetry import register_telemetry
from vito2mqtt.ports import OptolinkPort

TOPIC_PREFIX = "vito2mqtt"
"""Default MQTT topic prefix used by integration tests.

Matches the ``name`` passed to ``App(...)`` — the app uses this as the
topic prefix when ``mqtt.topic_prefix`` is unset in settings.
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_integration_app(adapter: FakeOptolinkAdapter) -> App:
    """Construct a fully-wired App backed by *adapter*.

    Mirrors the wiring in ``vito2mqtt.main`` but replaces:

    - ``JsonFileStore`` → ``MemoryStore()`` (no filesystem access)
    - concrete adapter factory → ``lambda: adapter`` (no serial I/O)
    """
    app = App(
        name="vito2mqtt",
        version=__version__,
        description="Viessmann boiler to MQTT bridge",
        settings_class=Vito2MqttSettings,
        store=MemoryStore(),
        adapters={OptolinkPort: lambda: adapter},
    )
    register_telemetry(app)
    register_commands(app)
    register_legionella(app)
    return app


async def run_app_briefly(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Vito2MqttSettings,
    *,
    wait: float = 0.3,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly.

    Returns after the background task has completed so callers can
    safely inspect ``mock_mqtt.published``.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(wait)
    shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_adapter() -> FakeOptolinkAdapter:
    """A fresh FakeOptolinkAdapter with no pre-configured responses."""
    return FakeOptolinkAdapter()


@pytest.fixture
def mock_mqtt() -> MockMqttClient:
    """A fresh MockMqttClient that records all publishes."""
    return MockMqttClient()


@pytest.fixture
def test_settings() -> Vito2MqttSettings:
    """Vito2MqttSettings with ultra-short polling intervals for fast tests.

    All per-domain polling intervals are set to 0.05 s so tests can observe
    published messages within a single asyncio.sleep(0.3) wait window.
    """
    return Vito2MqttSettings(
        serial_port="/dev/ttyUSB0",
        polling_outdoor=0.05,
        polling_hot_water=0.05,
        polling_burner=0.05,
        polling_heating_radiator=0.05,
        polling_heating_floor=0.05,
        polling_system=0.05,
        polling_diagnosis=0.05,
    )


@pytest.fixture
def integration_app(fake_adapter: FakeOptolinkAdapter) -> App:
    """A fully-wired App instance using in-memory doubles.

    Each test function gets a *fresh* App (fixture scope is ``"function"``)
    so tests are fully isolated.
    """
    return build_integration_app(fake_adapter)
