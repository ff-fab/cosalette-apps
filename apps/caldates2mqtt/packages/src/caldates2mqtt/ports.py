"""Hardware adapter ports for caldates2mqtt.

Defines Protocol classes for CalDAV interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """A single all-day calendar event.

    Attributes:
        title: Event summary.
        date: Event date (all-day events only).
    """

    title: str
    date: datetime.date


@runtime_checkable
class CalDavPort(Protocol):
    """Port for reading CalDAV calendar events.

    Implementations connect to a CalDAV server, fetch events within
    a lookahead window, filter to all-day events, and return them
    sorted by date ascending.
    """

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
        ...
