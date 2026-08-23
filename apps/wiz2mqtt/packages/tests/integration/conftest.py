"""Integration test fixtures for wiz2mqtt.

Provides a fully-wired App instance backed by FakeWizBulbAdapter and
MockMqttClient so integration tests can drive the real ``bulb_set``
command handler without real pywizlight or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, FakeClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.errors import error_type_map
from wiz2mqtt.main import bulb_set
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import Wiz2MqttSettings

TOPIC_PREFIX = "wiz2mqtt"
"""Default MQTT topic prefix used by integration tests."""

_DEFAULT_BULB: dict[str, object] = {"name": "office", "ip": "10.0.0.5"}


def build_integration_app(fake_adapter: FakeWizBulbAdapter) -> App:
    """Construct a fully-wired App with FakeWizBulbAdapter.

    Mirrors the command wiring in ``wiz2mqtt.main`` while substituting
    the adapter so tests stay isolated from real pywizlight I/O.
    """
    app = App(
        name="wiz2mqtt",
        settings_class=Wiz2MqttSettings,
        adapters={WizBulbPort: lambda: fake_adapter},
        error_type_map=error_type_map,
    )
    app.add_command(
        lambda settings: {bulb.name: bulb for bulb in settings.bulbs},
        bulb_set,
        summary="Apply a partial state update to a bulb",
    )
    return app


def make_settings(**bulb_overrides: object) -> Wiz2MqttSettings:
    """Isolated settings with a single bulb, ignoring host env/files."""
    bulb = {**_DEFAULT_BULB, **bulb_overrides}
    return Wiz2MqttSettings(bulbs=[bulb], _env_file=None, _config_file=None)  # type: ignore[arg-type,call-arg]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_adapter() -> FakeWizBulbAdapter:
    """A fresh FakeWizBulbAdapter."""
    return FakeWizBulbAdapter()


@pytest.fixture
def test_settings() -> Wiz2MqttSettings:
    """Isolated settings with a single bulb named 'office'."""
    return make_settings()


@pytest.fixture
def harness(
    fake_adapter: FakeWizBulbAdapter, test_settings: Wiz2MqttSettings
) -> AppHarness:
    """Fresh AppHarness wired with FakeWizBulbAdapter and one bulb."""
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=test_settings,
        shutdown_event=asyncio.Event(),
    )
