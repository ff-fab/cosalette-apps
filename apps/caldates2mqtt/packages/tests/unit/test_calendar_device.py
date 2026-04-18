"""Unit tests for caldates2mqtt calendar telemetry handler.

Test Techniques Used:
- Specification-based: Verify payload structure, event slicing, sort order
- Error Guessing: CalDavError propagation
"""

from __future__ import annotations

import datetime

import pytest

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.devices.calendar import make_calendar_telemetry
from caldates2mqtt.errors import CalDavConnectionError
from caldates2mqtt.ports import CalendarEvent
from caldates2mqtt.settings import CalendarConfig


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


@pytest.fixture
def fake_reader() -> FakeCalDavReader:
    return FakeCalDavReader()


@pytest.mark.unit
class TestCalendarTelemetryHappyPath:
    """Verify happy-path behavior of calendar telemetry handler."""

    async def test_returns_events_payload(
        self,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Handler reads events and returns correct payload structure."""
        events = [
            CalendarEvent(title="Gelber Sack", date=datetime.date(2026, 3, 27)),
            CalendarEvent(title="Restmuell", date=datetime.date(2026, 3, 31)),
        ]
        fake_reader.readings = [events]
        cal = _make_cal_config()
        handler = make_calendar_telemetry(cal)

        result = await handler(fake_reader)

        assert result == {
            "events": [
                {"title": "Gelber Sack", "date": "2026-03-27"},
                {"title": "Restmuell", "date": "2026-03-31"},
            ]
        }

    async def test_events_sliced_to_entries_count(
        self,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Events are sliced to configured entries count."""
        events = [
            CalendarEvent(title=f"Event {i}", date=datetime.date(2026, 4, i + 1))
            for i in range(10)
        ]
        fake_reader.readings = [events]
        cal = _make_cal_config(entries=3)
        handler = make_calendar_telemetry(cal)

        result = await handler(fake_reader)

        assert len(result["events"]) == 3  # type: ignore[arg-type]

    async def test_empty_calendar(
        self,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Empty calendar returns {"events": []}."""
        fake_reader.readings = [[]]
        cal = _make_cal_config()
        handler = make_calendar_telemetry(cal)

        result = await handler(fake_reader)

        assert result == {"events": []}

    async def test_fewer_events_than_entries(
        self,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Returns all available events when fewer than entries count."""
        events = [CalendarEvent(title="Only", date=datetime.date(2026, 4, 1))]
        fake_reader.readings = [events]
        cal = _make_cal_config(entries=5)
        handler = make_calendar_telemetry(cal)

        result = await handler(fake_reader)

        assert len(result["events"]) == 1  # type: ignore[arg-type]

    async def test_passes_correct_credentials(
        self,
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
        handler = make_calendar_telemetry(cal)

        await handler(fake_reader)

        assert fake_reader.calls[0] == (
            "https://cloud.test/dav/",
            "mytest",
            "testuser",
            "secret123",
            7,
        )


@pytest.mark.unit
class TestCalendarTelemetryErrorPropagation:
    """Verify errors propagate through the handler (framework handles retry)."""

    async def test_caldav_error_propagates(
        self,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """CalDavConnectionError from reader propagates to caller."""
        fake_reader.raise_on_next = CalDavConnectionError("server down")
        cal = _make_cal_config()
        handler = make_calendar_telemetry(cal)

        with pytest.raises(CalDavConnectionError, match="server down"):
            await handler(fake_reader)
