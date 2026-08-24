"""Integration test fixtures for wiz2mqtt.

Provides a fully-wired App instance backed by FakeWizBulbAdapter and
MockMqttClient so integration tests can drive the real ``bulb_set``
command handler without real pywizlight or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient, OnChange
from cosalette.testing import AppHarness, FakeClock

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import error_type_map
from wiz2mqtt.main import _bulb_map, bulb_set
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import Wiz2MqttSettings
from wiz2mqtt.state import SharedState

TOPIC_PREFIX = "wiz2mqtt"
"""Default MQTT topic prefix used by integration tests."""

_DEFAULT_BULB: dict[str, object] = {"name": "office", "ip": "10.0.0.5"}

_COMMAND_SETTLE_TIME = 0.03
"""Real seconds to wait after command injection for async dispatch to complete."""

_STARTUP_TIMEOUT = 2.0
"""Maximum seconds to wait for the harness to subscribe before timing out."""


def _shared_state_factory() -> SharedState:
    return SharedState()


def build_integration_app(fake_adapter: FakeWizBulbAdapter) -> App:
    """Construct a fully-wired App with FakeWizBulbAdapter.

    Mirrors the command and telemetry wiring in ``wiz2mqtt.main`` while
    substituting the adapter so tests stay isolated from real pywizlight I/O.
    """
    app = App(
        name="wiz2mqtt",
        settings_class=Wiz2MqttSettings,
        adapters={WizBulbPort: lambda: fake_adapter},
        error_type_map=error_type_map,
    )
    app.add_command(_bulb_map, bulb_set)
    app.state(_shared_state_factory)
    app.add_telemetry(
        _bulb_map,
        bulb_entity_tick,
        interval=0.01,
        publish=OnChange(),
    )
    return app


def make_settings(**bulb_overrides: object) -> Wiz2MqttSettings:
    """Isolated settings with a single bulb, ignoring host env/files."""
    bulb = {**_DEFAULT_BULB, **bulb_overrides}
    return Wiz2MqttSettings(bulbs=[bulb], _env_file=None, _config_file=None)  # type: ignore[arg-type,call-arg]


async def wait_until_subscribed(harness: AppHarness) -> None:
    """Poll until the harness has subscribed to command topics or time out.

    Avoids a fixed-duration startup sleep — returns as soon as the MQTT
    router is listening, keeping the suite fast even on slow CI runners.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _STARTUP_TIMEOUT
    while not harness.mqtt.subscriptions:
        if loop.time() >= deadline:
            raise AssertionError(
                f"App did not subscribe within {_STARTUP_TIMEOUT}s "
                "— router was not listening yet."
            )
        await asyncio.sleep(0.005)


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


@pytest.fixture
def settings_when_off() -> Wiz2MqttSettings:
    """Settings with when_unreachable='off' for the OFF-policy integration tests."""
    return make_settings(when_unreachable="off")


@pytest.fixture
def harness_when_off(
    fake_adapter: FakeWizBulbAdapter, settings_when_off: Wiz2MqttSettings
) -> AppHarness:
    """AppHarness wired with when_unreachable='off' settings."""
    return AppHarness(
        app=build_integration_app(fake_adapter),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=settings_when_off,
        shutdown_event=asyncio.Event(),
    )
