"""Integration test fixtures for caldates2mqtt.

Provides a fully-wired App instance backed by FakeCalDavReader and
MockMqttClient so integration tests can drive the real application logic
without real CalDAV or MQTT I/O.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import cosalette
import pytest
from cosalette import App, MockMqttClient
from cosalette.testing import AppHarness, FakeClock
from pydantic_settings import PydanticBaseSettingsSource

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import error_type_map
from caldates2mqtt.main import calendar
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
    "schedule": "*/3 * * * * ?",
}

_SECOND_CALENDAR: dict[str, Any] = {
    "key": "holidays",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "feiertage",
    "username": "testuser",
    "password": "testpass",
    "entries": 3,
    "days": 30,
    "schedule": "*/3 * * * * ?",
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

    Mirrors the telemetry wiring in ``caldates2mqtt.main`` while
    substituting the adapter and passing settings explicitly so tests
    stay isolated from the host environment.

    Args:
        fake_reader: FakeCalDavReader instance to inject.
        calendars: Calendar configurations to register as telemetries.
    """
    app = App(
        name="caldates2mqtt",
        settings_class=_FastPollSettings,
        adapters={CalDavPort: lambda: fake_reader},
        error_type_map=error_type_map,
    )

    def _make_handler(cal: CalendarConfig):
        async def _handler(
            trigger: cosalette.TriggerPayload,
            reader: CalDavPort,
            logger: logging.Logger,
        ) -> dict[str, object]:
            return await calendar(cal, trigger, reader, logger)

        return _handler

    for cal in calendars:
        app.add_telemetry(
            cal.key,
            _make_handler(cal),
            schedule=cal.schedule,
            triggerable=True,
        )
    return app


def make_harness(
    fake_reader: FakeCalDavReader,
    calendars: list[CalendarConfig],
    *,
    settings: CalDates2MqttSettings | None = None,
) -> AppHarness:
    """Construct an AppHarness wrapping the integration app.

    Args:
        fake_reader: FakeCalDavReader instance to inject.
        calendars: Calendar configurations to register as telemetries.
        settings: Optional settings override; defaults to _FastPollSettings
            with the provided calendars.
    """
    if settings is None:
        settings = _FastPollSettings(calendars=calendars)  # type: ignore[arg-type]
    return AppHarness(
        app=build_integration_app(fake_reader, calendars),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=settings,
        shutdown_event=asyncio.Event(),
    )


async def run_app_briefly(harness: AppHarness, *, wait: float = 0.3) -> None:
    """Start the harness as a background task, wait, then shut it down cleanly.

    Bounds task completion with asyncio.wait_for to prevent indefinite test hangs.
    """
    task = asyncio.create_task(harness.run())
    await asyncio.sleep(wait)
    harness.shutdown_event.set()
    await asyncio.wait_for(task, timeout=wait * 5)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_reader() -> FakeCalDavReader:
    """A fresh FakeCalDavReader with default event data."""
    return FakeCalDavReader()


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
def harness(
    fake_reader: FakeCalDavReader, test_settings: CalDates2MqttSettings
) -> AppHarness:
    """Fresh AppHarness with FakeCalDavReader and single-calendar settings."""
    return make_harness(fake_reader, test_settings.calendars, settings=test_settings)


@pytest.fixture
def multi_calendar_harness(
    fake_reader: FakeCalDavReader, multi_calendar_settings: CalDates2MqttSettings
) -> AppHarness:
    """Fresh AppHarness with FakeCalDavReader and two-calendar settings."""
    return make_harness(
        fake_reader, multi_calendar_settings.calendars, settings=multi_calendar_settings
    )
