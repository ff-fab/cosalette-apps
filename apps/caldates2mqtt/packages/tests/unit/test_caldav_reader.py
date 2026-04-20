"""Unit tests for caldates2mqtt.adapters.caldav_reader.

Test Techniques Used:
- Specification-based: Verify adapter return shape and URL construction
- Equivalence Partitioning: All-day events are kept while timed events are filtered
- Boundary Value Analysis: Date range end is derived from the requested days window
- Error Guessing: Upstream exceptions are translated into domain-specific errors
"""

from __future__ import annotations

import datetime
import socket
from types import SimpleNamespace

import caldav.lib.error
import niquests
import pytest

from caldates2mqtt.adapters import caldav_reader as caldav_reader_module
from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.errors import (
    CalDavAuthError,
    CalDavConnectionError,
    CalDavReadError,
    CalDavTimeoutError,
)
from caldates2mqtt.ports import CalendarEvent
from caldates2mqtt.settings import CalDates2MqttSettings


def _make_settings(timeout: float = 30.0) -> CalDates2MqttSettings:
    """Create minimal settings for CalDavReader tests."""
    return CalDates2MqttSettings(
        calendars=[
            {
                "key": "garbage",
                "url": "https://example.com/dav/",
                "calendar_name": "abfall",
                "username": "user",
                "password": "pass",
            }
        ],
        caldav_timeout=timeout,
    )


class _FakeEvent:
    """Minimal CalDAV event double matching the adapter's expectations."""

    def __init__(self, title: str, dtstart: datetime.date | datetime.datetime) -> None:
        self.instance = SimpleNamespace(
            vevent=SimpleNamespace(
                summary=SimpleNamespace(value=title),
                dtstart=SimpleNamespace(value=dtstart),
            )
        )
        self.loaded = False

    def load(self) -> None:
        self.loaded = True


@pytest.mark.unit
class TestCalDavReaderAsyncBoundary:
    """Verify the async adapter boundary and error translation."""

    async def test_read_events_returns_threaded_result(self) -> None:
        """read_events returns the result produced by _read_sync."""
        expected = [CalendarEvent(title="Pickup", date=datetime.date(2026, 4, 1))]
        reader = CalDavReader(_make_settings())

        def _read_sync(
            url: str,
            calendar_name: str,
            username: str,
            password: str,
            days: int,
        ) -> list[CalendarEvent]:
            assert (url, calendar_name, username, password, days) == (
                "https://example.com/dav/",
                "abfall",
                "user",
                "pass",
                14,
            )
            return expected

        reader._read_sync = _read_sync  # type: ignore[method-assign]

        result = await reader.read_events(
            "https://example.com/dav/",
            "abfall",
            "user",
            "pass",
            14,
        )

        assert result == expected

    @pytest.mark.parametrize(
        ("exc", "expected_error"),
        [
            (caldav.lib.error.AuthorizationError("denied"), CalDavAuthError),
            (niquests.ConnectionError("offline"), CalDavConnectionError),
            (niquests.Timeout("slow"), CalDavTimeoutError),
            (socket.timeout("slow"), CalDavTimeoutError),
        ],
    )
    async def test_read_events_maps_known_errors(
        self,
        exc: Exception,
        expected_error: type[Exception],
    ) -> None:
        """Known upstream exceptions are translated to domain errors."""
        reader = CalDavReader(_make_settings())

        def _raise(
            url: str,
            calendar_name: str,
            username: str,
            password: str,
            days: int,
        ) -> list[CalendarEvent]:
            raise exc

        reader._read_sync = _raise  # type: ignore[method-assign]

        with pytest.raises(expected_error, match=str(exc)):
            await reader.read_events(
                "https://example.com/dav/",
                "abfall",
                "user",
                "pass",
                14,
            )

    async def test_read_events_wraps_unknown_errors(self) -> None:
        """Unknown upstream exceptions are wrapped in CalDavReadError."""
        reader = CalDavReader(_make_settings())

        def _raise(
            url: str,
            calendar_name: str,
            username: str,
            password: str,
            days: int,
        ) -> list[CalendarEvent]:
            raise ValueError("bad payload")

        reader._read_sync = _raise  # type: ignore[method-assign]

        with pytest.raises(CalDavReadError, match="bad payload"):
            await reader.read_events(
                "https://example.com/dav/",
                "abfall",
                "user",
                "pass",
                14,
            )


@pytest.mark.unit
class TestCalDavReaderSyncParsing:
    """Verify synchronous CalDAV parsing and filtering."""

    def test_read_sync_filters_timed_events_and_sorts_results(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Timed events are filtered and all-day events are returned sorted."""
        calls: dict[str, object] = {}
        events = [
            _FakeEvent("  Restmuell  ", datetime.date(2026, 4, 5)),
            _FakeEvent("Timed", datetime.datetime(2026, 4, 2, 9, 30)),
            _FakeEvent("Gelber Sack", datetime.date(2026, 4, 1)),
        ]

        def fake_dav_client(
            *,
            url: str,
            username: str,
            password: str,
            timeout: float,
        ) -> object:
            calls["client"] = {
                "url": url,
                "username": username,
                "password": password,
                "timeout": timeout,
            }
            return object()

        class _FakeCalendar:
            def __init__(self, client: object, url: str) -> None:
                calls["calendar"] = {"client": client, "url": url}

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[_FakeEvent]:
                calls["search"] = {"start": start, "end": end, "expand": expand}
                return events

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _FakeCalendar)

        reader = CalDavReader(_make_settings(timeout=12.5))

        result = reader._read_sync(
            "https://example.com/dav/",
            "abfall",
            "user",
            "pass",
            10,
        )

        assert result == [
            CalendarEvent(title="Gelber Sack", date=datetime.date(2026, 4, 1)),
            CalendarEvent(title="Restmuell", date=datetime.date(2026, 4, 5)),
        ]
        assert calls["client"] == {
            "url": "https://example.com/dav/",
            "username": "user",
            "password": "pass",
            "timeout": 12.5,
        }
        assert calls["calendar"] == {
            "client": calls["calendar"]["client"],
            "url": "https://example.com/dav/abfall",
        }
        assert calls["search"]["expand"] is True
        assert (calls["search"]["end"] - calls["search"]["start"]).days == 10
        assert all(event.loaded for event in events)
