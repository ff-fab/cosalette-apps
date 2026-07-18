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
from cosalette.testing import AppHarness, FakeClock

from vito2mqtt import __version__
from vito2mqtt._registration import configure_app
from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
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
    configure_app(app)
    return app


def make_harness(adapter: FakeOptolinkAdapter | None = None) -> AppHarness:
    """Construct an AppHarness wrapping the integration app with *adapter*.

    Args:
        adapter: FakeOptolinkAdapter instance to inject. A fresh default
            adapter is created when not provided.
    """
    if adapter is None:
        adapter = FakeOptolinkAdapter()
    return AppHarness(
        app=build_integration_app(adapter),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=Vito2MqttSettings(
            serial_port="/dev/ttyUSB0",
            polling_outdoor=0.05,
            polling_hot_water=0.05,
            polling_burner=0.05,
            polling_heating_radiator=0.05,
            polling_heating_floor=0.05,
            polling_system=0.05,
            polling_diagnosis=0.05,
        ),
        shutdown_event=asyncio.Event(),
    )


async def run_app_briefly(harness: AppHarness, *, wait: float = 0.3) -> None:
    """Start the harness as a background task, wait, then shut it down cleanly.

    Returns after the background task has completed so callers can
    safely inspect ``harness.mqtt.published``.
    """
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(wait)
    harness.shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_adapter() -> FakeOptolinkAdapter:
    """A fresh FakeOptolinkAdapter with no pre-configured responses."""
    return FakeOptolinkAdapter()


@pytest.fixture
def harness(fake_adapter: FakeOptolinkAdapter) -> AppHarness:
    """Fresh AppHarness with FakeOptolinkAdapter and fast polling settings."""
    return make_harness(fake_adapter)
