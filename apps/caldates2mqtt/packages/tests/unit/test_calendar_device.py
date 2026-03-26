"""Unit tests for caldates2mqtt calendar device handler.

Test Techniques Used:
- Specification-based: Verify payload structure, event slicing, sort order
- State Transition: Shutdown during sleep, command handling
- Error Guessing: Invalid JSON payloads, CalDavError propagation
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging

import cosalette
import pytest
from cosalette.testing import FakeClock, MockMqttClient

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.devices.calendar import make_calendar_handler
from caldates2mqtt.errors import CalDavConnectionError
from caldates2mqtt.ports import CalDavPort, CalendarEvent
from caldates2mqtt.settings import CalendarConfig
from tests.fixtures.config import make_caldates2mqtt_settings

_logger = logging.getLogger("test")


def _make_cal_config(**overrides: object) -> CalendarConfig:
    """Create a CalendarConfig with sensible defaults for testing."""
    defaults: dict[str, object] = {
        "key": "garbage",
        "url": "https://example.com/dav/",
        "calendar_name": "abfall",
        "username": "user",
        "password": "pass",
        "entries": 5,
        "days": 14,
        "poll_interval": 0.01,
    }
    defaults.update(overrides)
    return CalendarConfig(**defaults)  # type: ignore[arg-type]


def _make_context(
    mock_mqtt: MockMqttClient,
    fake_clock: FakeClock,
    fake_reader: FakeCalDavReader,
    settings: cosalette.Settings | None = None,
) -> cosalette.DeviceContext:
    """Create a DeviceContext wired for calendar device tests."""
    if settings is None:
        settings = make_caldates2mqtt_settings()
    return cosalette.DeviceContext(
        name="garbage",
        settings=settings,
        mqtt=mock_mqtt,
        topic_prefix="caldates2mqtt",
        shutdown_event=asyncio.Event(),
        adapters={CalDavPort: fake_reader},
        clock=fake_clock,
    )


def _published_states(mock_mqtt: MockMqttClient) -> list[dict[str, object]]:
    """Extract all state payloads published to the calendar state topic."""
    return [
        json.loads(payload)
        for topic, payload, _retain, _qos in mock_mqtt.published
        if topic == "caldates2mqtt/garbage/state"
    ]


async def _run_handler_once(
    handler: object,
    ctx: cosalette.DeviceContext,
    reader: FakeCalDavReader,
) -> None:
    """Run handler as a task, let it publish once, then trigger shutdown."""
    task = asyncio.create_task(
        handler(ctx=ctx, reader=reader, logger=_logger)  # type: ignore[operator]
    )
    # Yield to let the handler run its first iteration
    for _ in range(10):
        await asyncio.sleep(0)
    ctx._shutdown_event.set()
    # Yield again so the handler exits its loop
    await asyncio.sleep(0)
    await task


@pytest.fixture
def fake_reader() -> FakeCalDavReader:
    return FakeCalDavReader()


@pytest.fixture
def mock_mqtt() -> MockMqttClient:
    return MockMqttClient()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.mark.unit
class TestCalendarDeviceHappyPath:
    """Verify happy-path behavior of calendar device handler."""

    async def test_publishes_events_payload(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Handler reads events and publishes correct payload structure."""
        events = [
            CalendarEvent(title="Gelber Sack", date=datetime.date(2026, 3, 27)),
            CalendarEvent(title="Restmuell", date=datetime.date(2026, 3, 31)),
        ]
        fake_reader.readings = [events]
        cal = _make_cal_config()
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        states = _published_states(mock_mqtt)
        assert len(states) >= 1
        assert states[0] == {
            "events": [
                {"title": "Gelber Sack", "date": "2026-03-27"},
                {"title": "Restmuell", "date": "2026-03-31"},
            ]
        }

    async def test_events_sliced_to_entries_count(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Events are sliced to configured entries count."""
        events = [
            CalendarEvent(title=f"Event {i}", date=datetime.date(2026, 4, i + 1))
            for i in range(10)
        ]
        fake_reader.readings = [events]
        cal = _make_cal_config(entries=3)
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        states = _published_states(mock_mqtt)
        assert len(states[0]["events"]) == 3  # type: ignore[arg-type]

    async def test_empty_calendar(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Empty calendar publishes {"events": []}."""
        fake_reader.readings = [[]]
        cal = _make_cal_config()
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        states = _published_states(mock_mqtt)
        assert states[0] == {"events": []}

    async def test_fewer_events_than_entries(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Returns all available events when fewer than entries count."""
        events = [CalendarEvent(title="Only", date=datetime.date(2026, 4, 1))]
        fake_reader.readings = [events]
        cal = _make_cal_config(entries=5)
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        states = _published_states(mock_mqtt)
        assert len(states[0]["events"]) == 1  # type: ignore[arg-type]

    async def test_passes_correct_credentials(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Handler passes url, calendar_name, username, password from config."""
        cal = _make_cal_config(
            url="https://cloud.test/dav/",
            calendar_name="mytest",
            username="testuser",
            password="secret123",
            days=7,
        )
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        assert fake_reader.calls[0] == (
            "https://cloud.test/dav/",
            "mytest",
            "testuser",
            "secret123",
            7,
        )


@pytest.mark.unit
class TestCalendarDeviceCommand:
    """Verify on-command re-read behavior."""

    async def test_reread_with_defaults(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Re-read command with empty payload uses configured defaults."""
        cal = _make_cal_config(entries=5, days=14)
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        # Trigger command
        assert ctx._command_handler is not None
        await ctx._command_handler("caldates2mqtt/garbage/set", "")

        # Verify reader was called with configured days
        assert fake_reader.calls[-1][4] == 14

    async def test_reread_with_overrides(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Re-read command with JSON payload overrides entries and days."""
        cal = _make_cal_config(entries=5, days=14)
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        await ctx._command_handler(
            "caldates2mqtt/garbage/set", '{"entries": 10, "days": 30}'
        )

        assert fake_reader.calls[-1][4] == 30

    async def test_reread_with_invalid_json(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Re-read command with invalid JSON falls back to defaults."""
        cal = _make_cal_config(entries=5, days=14)
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        await _run_handler_once(handler, ctx, fake_reader)

        await ctx._command_handler("caldates2mqtt/garbage/set", "not-json")

        assert fake_reader.calls[-1][4] == 14


@pytest.mark.unit
class TestCalendarDeviceErrorPropagation:
    """Verify errors propagate through the handler (not swallowed)."""

    async def test_caldav_error_propagates(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """CalDavConnectionError from reader propagates to caller."""
        fake_reader.raise_on_next = CalDavConnectionError("server down")
        cal = _make_cal_config()
        ctx = _make_context(mock_mqtt, fake_clock, fake_reader)
        handler = make_calendar_handler(cal)

        with pytest.raises(CalDavConnectionError, match="server down"):
            await handler(ctx=ctx, reader=fake_reader, logger=_logger)
