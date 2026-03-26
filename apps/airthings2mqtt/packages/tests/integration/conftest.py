"""Integration test fixtures for airthings2mqtt.

Provides a fully-wired App instance backed by FakeAirthingsReader and
MockMqttClient so integration tests can drive the real application logic
without real BLE or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.main import _poll_interval, _telemetry
from airthings2mqtt.ports import AirthingsReaderPort
from airthings2mqtt.settings import Airthings2MqttSettings
from tests.fixtures.config import make_airthings2mqtt_settings

TOPIC_PREFIX = "airthings2mqtt"
"""Default MQTT topic prefix used by integration tests."""

DEVICE_NAME = "airthings"
"""Default device name used in MQTT topics."""


def build_integration_app() -> App:
    """Construct a fully-wired App backed by FakeAirthingsReader.

    Mirrors the wiring in ``airthings2mqtt.main`` but forces the fake
    adapter so tests run without real BLE hardware.
    """
    test_app = App(
        name="airthings2mqtt",
        settings_class=Airthings2MqttSettings,
        adapters={AirthingsReaderPort: FakeAirthingsReader},
    )
    test_app.telemetry("airthings", interval=_poll_interval)(_telemetry)
    return test_app


async def run_app_briefly(
    test_app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Airthings2MqttSettings,
    *,
    wait: float = 0.3,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly."""
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        test_app._run_async(
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
def mock_mqtt() -> MockMqttClient:
    """A fresh MockMqttClient that records all publishes."""
    return MockMqttClient()


@pytest.fixture
def test_settings() -> Airthings2MqttSettings:
    """Isolated settings with minimum poll interval for fast tests."""
    return make_airthings2mqtt_settings(poll_interval=60)


@pytest.fixture
def integration_app() -> App:
    """Fully-wired App with FakeAirthingsReader for integration tests."""
    return build_integration_app()
