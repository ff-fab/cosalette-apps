"""Production CalDAV adapter for caldates2mqtt.

Connects to a CalDAV server, fetches events within a date range,
filters to all-day events, and returns sorted CalendarEvent objects.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from urllib.parse import urlparse

import caldav
import caldav.lib.error

from caldates2mqtt.errors import (
    ERROR_TYPE_MAP,
    CalDavError,
    CalDavNotFoundError,
    CalDavReadError,
)
from caldates2mqtt.ports import CalendarEvent
from caldates2mqtt.settings import CalDates2MqttSettings

_logger = logging.getLogger(__name__)


class CalDavReader:
    """Production adapter implementing CalDavPort.

    Creates a fresh DAVClient per call (stateless, no connection reuse).
    Runs the synchronous caldav library in a thread executor.

    Note: A fresh DAVClient (TCP+TLS handshake) is created per call. This is
    acceptable at the default ≥2-hour polling cadence. If polling is tightened
    to sub-minute intervals, introduce a cached session with lazy reconnect.
    """

    def __init__(self, settings: CalDates2MqttSettings) -> None:
        self._timeout = settings.caldav_timeout

    async def read_events(
        self,
        url: str,
        calendar_name: str,
        username: str,
        password: str,
        days: int,
    ) -> list[CalendarEvent]:
        """Read all-day events from a CalDAV calendar.

        Args:
            url: CalDAV server URL.
            calendar_name: Calendar name (path segment) on the server.
            username: CalDAV auth username.
            password: CalDAV auth password.
            days: Lookahead window in days from today.

        Returns:
            List of CalendarEvent sorted by date ascending.

        Raises:
            CalDavAuthError: If authentication fails.
            CalDavConnectionError: If the server is unreachable.
            CalDavTimeoutError: If the request times out.
            CalDavNotFoundError: If the calendar path does not exist on the server.
            CalDavReadError: For other CalDAV protocol errors.
        """
        try:
            return await asyncio.to_thread(
                self._read_sync, url, calendar_name, username, password, days
            )
        except CalDavError:
            raise
        except Exception as exc:
            mapped = ERROR_TYPE_MAP.get(type(exc))
            if mapped is not None:
                raise mapped(str(exc)) from exc
            raise CalDavReadError(str(exc)) from exc

    def _read_sync(
        self,
        url: str,
        calendar_name: str,
        username: str,
        password: str,
        days: int,
    ) -> list[CalendarEvent]:
        """Synchronous CalDAV fetch — called via asyncio.to_thread."""
        client = caldav.DAVClient(  # type: ignore
            url=url,
            username=username,
            password=password,
            timeout=self._timeout,
        )
        # Normalise URL: ensure one slash between base URL and calendar name.
        # Caught explicitly here (not via ERROR_TYPE_MAP) because the message
        # needs calendar_name and URL context unavailable at the async boundary.
        calendar_url = url.rstrip("/") + "/" + calendar_name.lstrip("/")
        calendar = caldav.Calendar(  # type: ignore
            client=client,
            url=calendar_url,
        )

        today = datetime.date.today()
        try:
            events = calendar.date_search(
                start=today,
                end=today + datetime.timedelta(days=days),
                expand=True,
            )
        except caldav.lib.error.NotFoundError as exc:
            parsed = urlparse(url)
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc += f":{parsed.port}"
            safe_url = parsed._replace(netloc=netloc).geturl()
            raise CalDavNotFoundError(
                f"calendar '{calendar_name}' not found on {safe_url} — "
                "check config or confirm the calendar exists server-side"
            ) from exc

        result: list[CalendarEvent] = []
        for event in events:
            # event.load() only if data not already populated (expand=True returns inline data).
            if not event.data:
                event.load()
            try:
                component = event.icalendar_component
                summary = str(component["SUMMARY"]).strip()
                dtstart = component["DTSTART"].dt
            except (KeyError, AttributeError) as exc:
                _logger.warning(
                    "Skipping malformed event in calendar '%s': %s",
                    calendar_name,
                    exc,
                )
                continue

            # Filter to all-day events only: date but not datetime
            if isinstance(dtstart, datetime.datetime):
                continue

            result.append(CalendarEvent(title=summary, date=dtstart))

        result.sort(key=lambda e: e.date)
        return result
