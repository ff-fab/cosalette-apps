"""Unit tests for caldates2mqtt ports — CalDavPort protocol and CalendarEvent.

Test Techniques Used:
- Specification-based: Protocol compliance, dataclass immutability
"""

from __future__ import annotations

import datetime

import pytest

from caldates2mqtt.ports import CalDavPort, CalendarEvent


@pytest.mark.unit
class TestCalendarEvent:
    """Verify CalendarEvent dataclass behavior."""

    def test_fields(self) -> None:
        """CalendarEvent has title and date fields."""
        event = CalendarEvent(title="Gelber Sack", date=datetime.date(2026, 3, 27))
        assert event.title == "Gelber Sack"
        assert event.date == datetime.date(2026, 3, 27)

    def test_frozen(self) -> None:
        """CalendarEvent is immutable."""
        event = CalendarEvent(title="Test", date=datetime.date(2026, 1, 1))
        with pytest.raises(AttributeError):
            event.title = "Modified"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two events with same values are equal."""
        a = CalendarEvent(title="X", date=datetime.date(2026, 1, 1))
        b = CalendarEvent(title="X", date=datetime.date(2026, 1, 1))
        assert a == b


@pytest.mark.unit
class TestCalDavPortProtocol:
    """Verify CalDavPort protocol compliance."""

    def test_caldav_reader_satisfies_protocol(self) -> None:
        """CalDavReader is a CalDavPort."""
        from caldates2mqtt.adapters.caldav_reader import CalDavReader

        assert issubclass(CalDavReader, CalDavPort)

    def test_fake_reader_satisfies_protocol(self) -> None:
        """FakeCalDavReader is a CalDavPort."""
        from caldates2mqtt.adapters.fake import FakeCalDavReader

        assert issubclass(FakeCalDavReader, CalDavPort)
