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
from cosalette import App, ClockPort, MockMqttClient
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, ManualClock
from pydantic_settings import PydanticBaseSettingsSource

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import (
    CalDavConnectionError,
    CalDavTimeoutError,
    error_type_map,
)
from caldates2mqtt.main import CalendarState, calendar
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


def calendar_config(key: str) -> CalendarConfig:
    """A fast-polling calendar configured under *key*."""
    return CalendarConfig(**{**_DEFAULT_CALENDAR, "key": key})


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
    *,
    min_interval: float | None = None,
    store: MemoryStore | None = None,
) -> App:
    """Construct a fully-wired App with FakeCalDavReader.

    Mirrors the telemetry wiring and ``app.discovery()`` in
    ``caldates2mqtt.main`` while substituting the adapter and passing
    settings explicitly so tests stay isolated from the host environment.
    Backed by a ``MemoryStore``: the discovery snapshot would otherwise
    persist on disk between tests and clear one test's calendars in the next.

    Args:
        fake_reader: FakeCalDavReader instance to inject.
        calendars: Calendar configurations to register as telemetries.
        min_interval: Optional ADR-066 trigger throttle.  Production uses
            ``main._TRIGGER_MIN_INTERVAL_SECONDS``; tests that assert throttle
            *behaviour* pass a fraction of a second so they stay fast.
        store: Optional discovery store. A shared store exercises cleanup of
            retained discovery configs after a configuration change.
    """
    app = App(
        name="caldates2mqtt",
        settings_class=_FastPollSettings,
        adapters={CalDavPort: lambda: fake_reader},
        error_type_map=error_type_map,
        store=store or MemoryStore(),
    )
    app.discovery()

    def _make_handler(cal: CalendarConfig):
        async def _handler(
            trigger: cosalette.TriggerPayload,
            reader: CalDavPort,
            logger: logging.Logger,
        ) -> CalendarState:
            return await calendar(cal, trigger, reader, logger)

        return _handler

    for cal in calendars:
        app.add_telemetry(
            cal.key,
            _make_handler(cal),
            schedule=cal.schedule,
            triggerable=True,
            min_interval=min_interval,
            retry=3,
            retry_on=(CalDavConnectionError, CalDavTimeoutError),
            state_model=CalendarState,
            unavailable_on=(CalDavConnectionError, CalDavTimeoutError),
        )
    return app


def make_harness(
    fake_reader: FakeCalDavReader,
    calendars: list[CalendarConfig],
    *,
    settings: CalDates2MqttSettings | None = None,
    min_interval: float | None = None,
    clock: ClockPort | None = None,
    store: MemoryStore | None = None,
) -> AppHarness:
    """Construct an AppHarness wrapping the integration app.

    Args:
        fake_reader: FakeCalDavReader instance to inject.
        calendars: Calendar configurations to register as telemetries.
        settings: Optional settings override; defaults to _FastPollSettings
            with the provided calendars.
        min_interval: Optional ADR-066 trigger throttle for the registrations.
        clock: Optional clock override; defaults to a gating ``ManualClock``.
        store: Optional discovery store shared across harness instances.
    """
    if settings is None:
        settings = _FastPollSettings(calendars=calendars)  # type: ignore[arg-type]
    return AppHarness(
        app=build_integration_app(
            fake_reader, calendars, min_interval=min_interval, store=store
        ),
        mqtt=MockMqttClient(),
        clock=clock or ManualClock(),
        settings=settings,
        shutdown_event=asyncio.Event(),
    )


async def run_app_briefly(
    harness: AppHarness,
    *,
    wait: float = 0.3,
    expected_publishes: dict[str, int] | None = None,
) -> None:
    """Start the harness, settle startup work, then shut it down.

    The gating :class:`ManualClock` lets startup telemetry settle without
    continuously releasing cron and retry sleeps while shutdown is in
    progress. Bounds publication waits and task completion to prevent hangs.
    """
    task = asyncio.create_task(harness.run())
    try:
        assert isinstance(harness.settings, CalDates2MqttSettings)
        first_calendar = harness.settings.calendars[0].key
        await harness.wait_for_publish_count(
            f"{TOPIC_PREFIX}/{first_calendar}/availability", 1
        )
        # Calendar runners are registered after discovery publication. Give
        # that bounded startup work time to reach its gated cron sleep before
        # moving virtual time.
        await asyncio.sleep(wait)
        await harness.advance_time(0)
        if expected_publishes is None:
            # Release one bounded cron/retry window. This preserves the error
            # publication exercised by the integration tests without letting
            # virtual sleeps free-run during teardown.
            for _ in range(4):
                await harness.advance_time(10)
                await asyncio.sleep(wait)
        else:
            await asyncio.wait_for(
                asyncio.gather(
                    *(
                        harness.wait_for_publish_count(topic, count)
                        for topic, count in expected_publishes.items()
                    )
                ),
                timeout=wait,
            )
    finally:
        harness.shutdown_event.set()
        try:
            await asyncio.wait_for(task, timeout=wait * 5)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


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
