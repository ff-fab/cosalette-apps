"""Integration test fixtures for caldates2mqtt.

Provides a fully-wired App instance backed by FakeCalDavReader and
MockMqttClient so integration tests can drive the real application logic
without real CalDAV or MQTT I/O.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cosalette import App, MockMqttClient
from pydantic_settings import PydanticBaseSettingsSource

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.devices.calendar import make_calendar_handler
from caldates2mqtt.ports import CalDavPort
from caldates2mqtt.settings import CalDates2MqttSettings, CalendarConfig

TOPIC_PREFIX = "caldates2mqtt"
"""Default MQTT topic prefix used by integration tests."""

_DEFAULT_CALENDAR: dict[str, Any] = {
    "key": "garbage",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "abfall_shared_by_fab",
    "username": "testuser",
    "password": "testpass",
    "entries": 5,
    "days": 14,
    "poll_interval": 0.05,
}

_SECOND_CALENDAR: dict[str, Any] = {
    "key": "holidays",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "feiertage",
    "username": "testuser",
    "password": "testpass",
    "entries": 3,
    "days": 30,
    "poll_interval": 0.05,
}


class _FastPollSettings(CalDates2MqttSettings):
    """Settings subclass that ignores env vars for deterministic tests.

    Overrides settings sources so integration tests are isolated from
    the host environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[CalDates2MqttSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def build_integration_app(
    fake_reader: FakeCalDavReader,
    calendars: list[CalendarConfig],
) -> App:
    """Construct a fully-wired App with FakeCalDavReader.

    Mirrors the wiring in ``caldates2mqtt.main`` but substitutes the
    adapter and constructs settings independently so we avoid the
    eager ``_settings`` construction at module level.

    Args:
        fake_reader: FakeCalDavReader instance to inject.
        calendars: Calendar configurations to register as devices.
    """
    app = App(
        name="caldates2mqtt",
        settings_class=_FastPollSettings,
        adapters={CalDavPort: lambda: fake_reader},
    )
    for cal in calendars:
        app.add_device(cal.key, make_calendar_handler(cal))
    return app


async def run_app_briefly(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: CalDates2MqttSettings,
    *,
    wait: float = 0.3,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly."""
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
def fake_reader() -> FakeCalDavReader:
    """A fresh FakeCalDavReader with default event data."""
    return FakeCalDavReader()


@pytest.fixture
def mock_mqtt() -> MockMqttClient:
    """A fresh MockMqttClient that records all publishes."""
    return MockMqttClient()


@pytest.fixture
def test_settings() -> CalDates2MqttSettings:
    """Isolated settings with a single calendar and fast poll interval."""
    return _FastPollSettings(calendars=[_DEFAULT_CALENDAR])  # type: ignore[return-value]


@pytest.fixture
def multi_calendar_settings() -> CalDates2MqttSettings:
    """Isolated settings with two calendars for multi-device tests."""
    return _FastPollSettings(  # type: ignore[return-value]
        calendars=[_DEFAULT_CALENDAR, _SECOND_CALENDAR],
    )


@pytest.fixture
def integration_app(
    fake_reader: FakeCalDavReader, test_settings: CalDates2MqttSettings
) -> App:
    """Fully-wired App with FakeCalDavReader for single-calendar tests."""
    return build_integration_app(fake_reader, test_settings.calendars)
