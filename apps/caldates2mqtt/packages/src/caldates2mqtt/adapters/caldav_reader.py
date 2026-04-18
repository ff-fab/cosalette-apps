"""Production CalDAV adapter for caldates2mqtt.

Connects to a CalDAV server, fetches events within a date range,
filters to all-day events, and returns sorted CalendarEvent objects.
"""

from __future__ import annotations

import asyncio
import datetime

import caldav

from caldates2mqtt.errors import ERROR_TYPE_MAP, CalDavReadError
from caldates2mqtt.ports import CalendarEvent
from caldates2mqtt.settings import CalDates2MqttSettings


class CalDavReader:
    """Production adapter implementing CalDavPort.

    Creates a fresh DAVClient per call (stateless, no connection reuse).
    Runs the synchronous caldav library in a thread executor.
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
            CalDavReadError: For other CalDAV protocol errors.
        """
        try:
            return await asyncio.to_thread(
                self._read_sync, url, calendar_name, username, password, days
            )
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
        calendar = caldav.Calendar(  # type: ignore
            client=client,
            url=f"{url}{calendar_name}",
        )

        today = datetime.date.today()
        events = calendar.date_search(
            start=today,
            end=today + datetime.timedelta(days=days),
            expand=True,
        )

        result: list[CalendarEvent] = []
        for event in events:
            event.load()
            vevent = event.instance.vevent
            summary = vevent.summary.value.strip()
            dtstart = vevent.dtstart.value

            # Filter to all-day events only: date but not datetime
            if isinstance(dtstart, datetime.datetime):
                continue

            result.append(CalendarEvent(title=summary, date=dtstart))

        result.sort(key=lambda e: e.date)
        return result
