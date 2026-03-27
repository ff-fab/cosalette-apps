"""Unit tests for caldates2mqtt adapters — FakeCalDavReader.

Test Techniques Used:
- Specification-based: Verify protocol compliance, default behavior, cycling
- State Transition: raise_on_next → read → error → cleared
"""

from __future__ import annotations

import datetime

import pytest

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import CalDavConnectionError
from caldates2mqtt.ports import CalendarEvent


@pytest.mark.unit
class TestFakeCalDavReader:
    """Verify FakeCalDavReader satisfies CalDavPort protocol."""

    async def test_default_events(self) -> None:
        """Default reading returns two sample events."""
        reader = FakeCalDavReader()
        events = await reader.read_events(
            "https://example.com/", "cal", "user", "pass", 14
        )
        assert len(events) == 2
        assert events[0].title == "Gelber Sack"
        assert events[1].title == "Restmuell"

    async def test_records_calls(self) -> None:
        """read_events() records the arguments passed."""
        reader = FakeCalDavReader()
        await reader.read_events("https://example.com/", "cal", "user", "pass", 14)
        assert reader.calls == [("https://example.com/", "cal", "user", "pass", 14)]

    async def test_cycling_through_readings(self) -> None:
        """Reader cycles through provided event lists."""
        list_a = [CalendarEvent(title="A", date=datetime.date(2026, 1, 1))]
        list_b = [CalendarEvent(title="B", date=datetime.date(2026, 1, 2))]
        reader = FakeCalDavReader()
        reader.readings = [list_a, list_b]

        first = await reader.read_events("u", "c", "n", "p", 7)
        second = await reader.read_events("u", "c", "n", "p", 7)
        third = await reader.read_events("u", "c", "n", "p", 7)

        assert first == list_a
        assert second == list_b
        assert third == list_a  # cycles back

    async def test_raise_on_next(self) -> None:
        """raise_on_next causes the next read to raise, then clears.

        Technique: State Transition — error state is transient.
        """
        reader = FakeCalDavReader()
        reader.raise_on_next = CalDavConnectionError("server down")

        with pytest.raises(CalDavConnectionError, match="server down"):
            await reader.read_events("u", "c", "n", "p", 7)

        # Subsequent read succeeds
        events = await reader.read_events("u", "c", "n", "p", 7)
        assert len(events) == 2

    async def test_raise_on_next_records_call(self) -> None:
        """Arguments are recorded even when raise_on_next fires."""
        reader = FakeCalDavReader()
        reader.raise_on_next = CalDavConnectionError("fail")

        with pytest.raises(CalDavConnectionError):
            await reader.read_events("u", "c", "n", "p", 7)

        assert reader.calls == [("u", "c", "n", "p", 7)]
