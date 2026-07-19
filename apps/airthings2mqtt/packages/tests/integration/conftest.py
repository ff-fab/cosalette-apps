"""Integration test fixtures for airthings2mqtt.

Provides a fully-wired App instance backed by FakeAirthingsReader and
MockMqttClient so integration tests can drive the real application logic
without real BLE or MQTT I/O.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, FakeClock

from pydantic import Field
from pydantic_settings import PydanticBaseSettingsSource

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from cosalette import setting_ref

from airthings2mqtt.main import _telemetry
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
    test_app.telemetry(
        "airthings",
        interval=setting_ref("poll_interval"),
        triggerable=True,
    )(_telemetry)
    return test_app


def make_harness(
    *,
    adapter: type | object = FakeAirthingsReader,
    settings: Airthings2MqttSettings | None = None,
) -> AppHarness:
    """Construct an AppHarness wrapping the app with the given reader adapter.

    Args:
        adapter: Adapter class/factory for AirthingsReaderPort (default
            FakeAirthingsReader).
        settings: Optional settings override; defaults to fast-poll test
            settings (poll_interval=1).
    """
    return AppHarness(
        app=build_integration_app(adapter=adapter),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=settings
        or _FastPollSettings(device_mac="AA:BB:CC:DD:EE:FF", poll_interval=1),  # type: ignore[arg-type]
        shutdown_event=asyncio.Event(),
    )


async def run_app_briefly(harness: AppHarness, *, wait: float = 0.3) -> None:
    """Start the harness as a background task, wait, then shut it down cleanly."""
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(wait)
    harness.shutdown_event.set()
    await task


def make_long_poll_settings() -> Airthings2MqttSettings:
    """Settings with a 1-hour poll interval for trigger-causality tests.

    A 3600-second poll cannot fire within the test's 2-second window, so
    the second state publish is guaranteed to be the triggered re-read,
    not an accidental scheduler tick.
    """
    return _FastPollSettings(device_mac="AA:BB:CC:DD:EE:FF", poll_interval=3600)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_settings() -> Airthings2MqttSettings:
    """Isolated settings with very short poll interval for fast tests."""
    return _FastPollSettings(device_mac="AA:BB:CC:DD:EE:FF", poll_interval=1)  # type: ignore[return-value]


@pytest.fixture
def harness() -> AppHarness:
    """Fresh AppHarness with FakeAirthingsReader and fast poll settings."""
    return make_harness()
