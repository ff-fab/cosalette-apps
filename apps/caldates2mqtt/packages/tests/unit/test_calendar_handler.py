"""Unit tests for caldates2mqtt calendar telemetry handler.

Test Techniques Used:
- Specification-based: Verify payload structure, event slicing, credentials
- Equivalence Partitioning: Trigger payload variants (valid, invalid, empty)
- Boundary Value Analysis: Trigger override limits for entries and days
- Error Guessing: Invalid JSON payloads, CalDavError propagation
"""

from __future__ import annotations

import datetime
import logging

import cosalette
import pytest

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import CalDavConnectionError
from caldates2mqtt.main import calendar
from caldates2mqtt.ports import CalendarEvent
from caldates2mqtt.settings import CalendarConfig

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
        "schedule": "*/10 * * * * ?",
    }
    defaults.update(overrides)
    return CalendarConfig(**defaults)  # type: ignore[arg-type]


def _make_events(count: int) -> list[CalendarEvent]:
    """Create a sequence of deterministic CalendarEvent objects."""
    start = datetime.date(2026, 4, 1)
    return [
        CalendarEvent(
            title=f"Event {index}", date=start + datetime.timedelta(days=index)
        )
        for index in range(count)
    ]


@pytest.fixture
def fake_reader() -> FakeCalDavReader:
    return FakeCalDavReader()


@pytest.mark.unit
class TestCalendarHandlerHappyPath:
    """Verify happy-path behavior of calendar telemetry handler."""

    async def test_returns_events_payload(self, fake_reader: FakeCalDavReader) -> None:
        """Handler reads events and returns correct payload structure."""
        events = [
            CalendarEvent(title="Gelber Sack", date=datetime.date(2026, 3, 27)),
            CalendarEvent(title="Restmuell", date=datetime.date(2026, 3, 31)),
        ]
        fake_reader.readings = [events]

        result = await calendar(
            cal=_make_cal_config(),
            trigger=cosalette.TriggerPayload.scheduled(),
            reader=fake_reader,
            logger=_logger,
        )

        assert result == {
            "events": [
                {"title": "Gelber Sack", "date": "2026-03-27"},
                {"title": "Restmuell", "date": "2026-03-31"},
            ]
        }

    async def test_events_sliced_to_entries_count(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Events are sliced to configured entries count."""
        fake_reader.readings = [_make_events(10)]

        result = await calendar(
            cal=_make_cal_config(entries=3),
            trigger=cosalette.TriggerPayload.scheduled(),
            reader=fake_reader,
            logger=_logger,
        )

        assert len(result["events"]) == 3  # type: ignore[arg-type]

    async def test_empty_calendar(self, fake_reader: FakeCalDavReader) -> None:
        """Empty calendar returns {"events": []}."""
        fake_reader.readings = [[]]

        result = await calendar(
            cal=_make_cal_config(),
            trigger=cosalette.TriggerPayload.scheduled(),
            reader=fake_reader,
            logger=_logger,
        )

        assert result == {"events": []}

    async def test_fewer_events_than_entries(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Returns all available events when fewer than entries count."""
        events = [CalendarEvent(title="Only", date=datetime.date(2026, 4, 1))]
        fake_reader.readings = [events]

        result = await calendar(
            cal=_make_cal_config(entries=5),
            trigger=cosalette.TriggerPayload.scheduled(),
            reader=fake_reader,
            logger=_logger,
        )

        assert len(result["events"]) == 1  # type: ignore[arg-type]

    async def test_passes_correct_credentials(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Handler passes url, calendar_name, username, password from config."""
        await calendar(
            cal=_make_cal_config(
                url="https://cloud.test/dav/",
                calendar_name="mytest",
                username="testuser",
                password="secret123",
                days=7,
            ),
            trigger=cosalette.TriggerPayload.scheduled(),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[0] == (
            "https://cloud.test/dav/",
            "mytest",
            "testuser",
            "secret123",
            7,
        )


@pytest.mark.unit
class TestCalendarHandlerTrigger:
    """Verify trigger-based re-read behavior via TriggerPayload."""

    async def test_trigger_with_empty_payload_uses_defaults(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Trigger with empty payload uses configured defaults."""
        await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt(""),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 14

    async def test_trigger_with_overrides(self, fake_reader: FakeCalDavReader) -> None:
        """Trigger with JSON payload overrides entries and days."""
        fake_reader.readings = [_make_events(15)]

        result = await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt('{"entries": 10, "days": 30}'),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 30
        assert len(result["events"]) == 10  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("raw_entries", "expected_count"),
        [(50, 50), (51, 50)],
    )
    async def test_trigger_entries_override_respects_upper_boundary(
        self,
        fake_reader: FakeCalDavReader,
        raw_entries: int,
        expected_count: int,
    ) -> None:
        """Trigger entries override respects the upper boundary.

        Technique: Boundary Value Analysis — exact max and just-above-max input.
        """
        fake_reader.readings = [_make_events(60)]

        result = await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt(
                f'{{"entries": {raw_entries}, "days": 30}}'
            ),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 30
        assert len(result["events"]) == expected_count  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("raw_days", "expected_days"),
        [(365, 365), (366, 365)],
    )
    async def test_trigger_days_override_respects_upper_boundary(
        self,
        fake_reader: FakeCalDavReader,
        raw_days: int,
        expected_days: int,
    ) -> None:
        """Trigger days override respects the upper boundary.

        Technique: Boundary Value Analysis — exact max and just-above-max input.
        """
        await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt(f'{{"days": {raw_days}}}'),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == expected_days

    async def test_trigger_with_invalid_json(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Trigger with invalid JSON falls back to defaults."""
        await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt("not-json"),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 14

    async def test_trigger_ignores_invalid_override_types(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Trigger with non-int or negative overrides uses defaults."""
        await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt(
                '{"entries": "ten", "days": -1}'
            ),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 14

    async def test_trigger_with_non_dict_json(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """Trigger with valid JSON but non-dict value falls back to defaults."""
        await calendar(
            cal=_make_cal_config(entries=5, days=14),
            trigger=cosalette.TriggerPayload.from_mqtt('"just a string"'),
            reader=fake_reader,
            logger=_logger,
        )

        assert fake_reader.calls[-1][4] == 14


@pytest.mark.unit
class TestCalendarHandlerErrorPropagation:
    """Verify errors propagate through the handler (not swallowed)."""

    async def test_caldav_error_propagates(self, fake_reader: FakeCalDavReader) -> None:
        """CalDavConnectionError from reader propagates to caller."""
        fake_reader.raise_on_next = CalDavConnectionError("server down")

        with pytest.raises(CalDavConnectionError, match="server down"):
            await calendar(
                cal=_make_cal_config(),
                trigger=cosalette.TriggerPayload.scheduled(),
                reader=fake_reader,
                logger=_logger,
            )
