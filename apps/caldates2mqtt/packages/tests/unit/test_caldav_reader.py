"""Unit tests for caldates2mqtt.adapters.caldav_reader.

Test Techniques Used:
- Specification-based: Verify adapter return shape and URL construction
- Equivalence Partitioning: All-day events are kept while timed events are filtered
- Boundary Value Analysis: Date range end is derived from the requested days window
- Error Guessing: Upstream exceptions are translated into domain-specific errors
"""

from __future__ import annotations

import datetime
import re
import socket
from types import SimpleNamespace
from urllib.parse import urlparse

import caldav.lib.error
import niquests
import pytest

from caldates2mqtt.adapters import caldav_reader as caldav_reader_module
from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.errors import (
    CalDavAuthError,
    CalDavConnectionError,
    CalDavError,
    CalDavNotFoundError,
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
        self._icalendar_component = {
            "SUMMARY": title,
            "DTSTART": SimpleNamespace(dt=dtstart),
        }
        self.loaded = False
        self.data: bytes | None = None  # simulate server not returning inline data

    @property
    def icalendar_component(self) -> dict[str, object]:
        return self._icalendar_component

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

        with pytest.raises(expected_error) as exc_info:
            await reader.read_events(
                "https://example.com/dav/",
                "abfall",
                "user",
                "pass",
                14,
            )

        # Message is built from safe parts only (upstream class name + calendar
        # + sanitized host), never the raw str(exc) which could embed the URL.
        msg = str(exc_info.value)
        assert type(exc).__name__ in msg
        assert "abfall" in msg
        assert "example.com" in msg

    @pytest.mark.parametrize(
        ("domain_exc", "expected_type"),
        [
            (CalDavNotFoundError("calendar 'x' not found"), CalDavNotFoundError),
            (CalDavAuthError("denied"), CalDavAuthError),
            (CalDavConnectionError("offline"), CalDavConnectionError),
            (CalDavTimeoutError("slow"), CalDavTimeoutError),
            (CalDavReadError("parse error"), CalDavReadError),
        ],
    )
    async def test_read_events_passes_through_caldav_errors(
        self,
        domain_exc: CalDavError,
        expected_type: type[CalDavError],
    ) -> None:
        """CalDavError subclasses raised by _read_sync are NOT re-wrapped in CalDavReadError."""
        reader = CalDavReader(_make_settings())

        def _raise(
            url: str,
            calendar_name: str,
            username: str,
            password: str,
            days: int,
        ) -> list[CalendarEvent]:
            raise domain_exc

        reader._read_sync = _raise  # type: ignore[method-assign]

        with pytest.raises(expected_type, match=re.escape(str(domain_exc))):
            await reader.read_events(
                "https://example.com/dav/",
                "x",
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

        with pytest.raises(CalDavReadError) as exc_info:
            await reader.read_events(
                "https://example.com/dav/",
                "abfall",
                "user",
                "pass",
                14,
            )

        # Unknown upstream text ("bad payload") is dropped; only the safe class
        # name + calendar + host are surfaced.
        msg = str(exc_info.value)
        assert "ValueError" in msg
        assert "abfall" in msg
        assert "bad payload" not in msg

    async def test_read_events_strips_credentials_from_mapped_error(self) -> None:
        """Mapped (opted-in) errors must not leak URL credentials into the message.

        Technique: Security / Error Guessing — the message is published to the
        MQTT error topic via error_type_map, so a URL with embedded userinfo
        must never appear verbatim (LEAK-01 hardening).
        """
        reader = CalDavReader(_make_settings())

        def _raise(
            url: str,
            calendar_name: str,
            username: str,
            password: str,
            days: int,
        ) -> list[CalendarEvent]:
            raise niquests.ConnectionError(
                "connection to https://admin:s3cr3t@host failed"
            )

        reader._read_sync = _raise  # type: ignore[method-assign]

        with pytest.raises(CalDavConnectionError) as exc_info:
            await reader.read_events(
                "https://admin:s3cr3t@example.com:8443/dav/?token=abc",
                "abfall",
                "admin",
                "s3cr3t",
                14,
            )

        msg = str(exc_info.value)
        assert "s3cr3t" not in msg, f"Credential leaked: {msg}"
        assert "admin:" not in msg, f"Userinfo leaked: {msg}"
        assert "token=abc" not in msg, f"Query token leaked: {msg}"
        assert "example.com" in msg


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

    def test_read_sync_raises_not_found_error_on_404(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """NotFoundError from caldav is translated to CalDavNotFoundError with context."""

        def fake_dav_client(**kwargs: object) -> object:
            return object()

        class _FailingCalendar:
            def __init__(self, client: object, url: str) -> None:
                pass

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[object]:
                raise caldav.lib.error.NotFoundError("404")

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _FailingCalendar)

        reader = CalDavReader(_make_settings())

        with pytest.raises(
            CalDavNotFoundError, match=r"contact_birthdays.*https://example\.com/dav/"
        ):
            reader._read_sync(
                "https://example.com/dav/",
                "contact_birthdays",
                "user",
                "pass",
                14,
            )

    def test_read_sync_not_found_strips_credentials_from_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CalDavNotFoundError message contains host:port but NOT embedded credentials."""

        def fake_dav_client(**kwargs: object) -> object:
            return object()

        class _FailingCalendar:
            def __init__(self, client: object, url: str) -> None:
                pass

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[object]:
                raise caldav.lib.error.NotFoundError("404")

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _FailingCalendar)

        reader = CalDavReader(_make_settings())

        with pytest.raises(CalDavNotFoundError) as exc_info:
            reader._read_sync(
                "https://admin:s3cr3t@example.com:8443/dav/",
                "cal",
                "admin",
                "s3cr3t",
                7,
            )

        msg = str(exc_info.value)
        # Parse the sanitized URL out of the known message format rather than
        # using substring matching — avoids py/incomplete-url-substring-sanitization.
        safe_url_in_msg = msg.split(" not found on ", 1)[1].split(" — ", 1)[0]
        parsed_safe = urlparse(safe_url_in_msg)
        assert parsed_safe.hostname == "example.com"
        assert parsed_safe.port == 8443
        assert "s3cr3t" not in msg, (
            f"Credential must not appear in error message, got: {msg}"
        )
        assert "admin:" not in msg, (
            f"Credential must not appear in error message, got: {msg}"
        )

    def test_read_sync_skips_malformed_events(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Malformed events (missing SUMMARY or DTSTART) are skipped with a warning."""

        class _MalformedEvent:
            data = b"fake"  # pretend inline data already populated

            @property
            def icalendar_component(self) -> dict[str, object]:
                return {}  # missing SUMMARY and DTSTART

            def load(self) -> None:
                pass  # pragma: no cover

        class _GoodEvent:
            data = b"fake"

            @property
            def icalendar_component(self) -> dict[str, object]:
                return {
                    "SUMMARY": "Good Event",
                    "DTSTART": SimpleNamespace(dt=datetime.date(2026, 4, 1)),
                }

            def load(self) -> None:
                pass  # pragma: no cover

        def fake_dav_client(**kwargs: object) -> object:
            return object()

        class _Calendar:
            def __init__(self, client: object, url: str) -> None:
                pass

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[object]:
                return [_MalformedEvent(), _GoodEvent()]

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _Calendar)

        reader = CalDavReader(_make_settings())
        result = reader._read_sync(
            "https://example.com/dav/",
            "abfall",
            "user",
            "pass",
            10,
        )

        assert result == [
            CalendarEvent(title="Good Event", date=datetime.date(2026, 4, 1))
        ]
        assert any("Skipping malformed event" in r.message for r in caplog.records), (
            "Expected a warning about the skipped malformed event"
        )

    def test_read_sync_does_not_load_when_data_already_populated(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Events with inline data (from expand=True) do not trigger an extra load()."""
        event = _FakeEvent("Event", datetime.date(2026, 4, 1))
        event.data = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"  # simulate populated

        def fake_dav_client(**kwargs: object) -> object:
            return object()

        class _FakeCalendar:
            def __init__(self, client: object, url: str) -> None:
                pass

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[_FakeEvent]:
                return [event]

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _FakeCalendar)

        reader = CalDavReader(_make_settings())
        reader._read_sync("https://example.com/dav/", "abfall", "user", "pass", 10)

        assert not event.loaded, (
            "load() must not be called when event.data is already populated"
        )

    @pytest.mark.parametrize(
        ("url", "calendar_name", "expected_url"),
        [
            (
                "https://example.com/dav/",
                "abfall",
                "https://example.com/dav/abfall",
            ),
            (
                "https://example.com/dav",  # no trailing slash
                "abfall",
                "https://example.com/dav/abfall",
            ),
            (
                "https://example.com/dav/",
                "/abfall",  # leading slash
                "https://example.com/dav/abfall",
            ),
            (
                "https://example.com/dav",  # both cases
                "/abfall",
                "https://example.com/dav/abfall",
            ),
        ],
    )
    def test_read_sync_constructs_calendar_url(
        self,
        monkeypatch: pytest.MonkeyPatch,
        url: str,
        calendar_name: str,
        expected_url: str,
    ) -> None:
        """calendar_url is correctly formed regardless of trailing/leading slash conventions."""
        captured: dict[str, str] = {}

        def fake_dav_client(**kwargs: object) -> object:
            return object()

        class _CapturingCalendar:
            def __init__(self, client: object, url: str) -> None:
                captured["url"] = url

            def date_search(
                self,
                *,
                start: datetime.date,
                end: datetime.date,
                expand: bool,
            ) -> list[object]:
                return []

        monkeypatch.setattr(caldav_reader_module.caldav, "DAVClient", fake_dav_client)
        monkeypatch.setattr(caldav_reader_module.caldav, "Calendar", _CapturingCalendar)

        reader = CalDavReader(_make_settings())
        reader._read_sync(url, calendar_name, "user", "pass", 7)

        assert captured["url"] == expected_url
