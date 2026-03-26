"""Integration test fixtures for airthings2mqtt.

Provides a fully-wired App instance backed by FakeAirthingsReader and
MockMqttClient so integration tests can drive the real application logic
without real BLE or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient

from pydantic import Field
from pydantic_settings import PydanticBaseSettingsSource

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.main import _poll_interval, _telemetry
from airthings2mqtt.ports import AirthingsReaderPort
from airthings2mqtt.settings import Airthings2MqttSettings

TOPIC_PREFIX = "airthings2mqtt"
"""Default MQTT topic prefix used by integration tests."""

DEVICE_NAME = "airthings"
"""Default device name used in MQTT topics."""


class _FastPollSettings(Airthings2MqttSettings):
    """Settings subclass that allows sub-60s poll intervals for testing.

    Overrides both ``poll_interval`` validation (removes ge=60) and
    settings sources (ignores env vars / .env files) so integration
    tests can use very short poll intervals deterministically.
    """

    poll_interval: int = Field(  # type: ignore[assignment]
        default=1,
        ge=1,
        description="Poll interval in seconds (relaxed for tests)",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[Airthings2MqttSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def build_integration_app(
    adapter: type | object = FakeAirthingsReader,
) -> App:
    """Construct a fully-wired App with the given reader adapter.

    Mirrors the wiring in ``airthings2mqtt.main`` but substitutes the
    adapter so tests run without real BLE hardware.

    Args:
        adapter: Adapter class or factory callable for AirthingsReaderPort.
            Defaults to FakeAirthingsReader.
    """
    test_app = App(
        name="airthings2mqtt",
        settings_class=Airthings2MqttSettings,
        adapters={AirthingsReaderPort: adapter},
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
    """Isolated settings with very short poll interval for fast tests."""
    return _FastPollSettings(device_mac="AA:BB:CC:DD:EE:FF", poll_interval=1)  # type: ignore[return-value]


@pytest.fixture
def integration_app() -> App:
    """Fully-wired App with FakeAirthingsReader for integration tests."""
    return build_integration_app()
