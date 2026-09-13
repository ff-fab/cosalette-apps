"""Fake CalDAV reader adapter for testing and dry-run mode.

Provides deterministic events for unit tests and --dry-run operation.
Supports cycling through multiple event lists and raising errors on demand.
"""

from __future__ import annotations

import datetime

from caldates2mqtt.ports import CalendarEvent

_tomorrow = datetime.date.today() + datetime.timedelta(days=1)
_in_five_days = datetime.date.today() + datetime.timedelta(days=5)

_DEFAULT_EVENTS: list[CalendarEvent] = [
    CalendarEvent(title="Gelber Sack", date=_tomorrow),
    CalendarEvent(title="Restmuell", date=_in_five_days),
]


class FakeCalDavReader:
    """Test double for CalDavPort.

    Returns configurable, deterministic event lists. Supports:
    - Default values (two sample garbage collection events)
    - Cycling through a list of event lists
    - Raising a specific error on the next read

    Attributes:
        readings: List of event lists to cycle through.
        calls: List of (url, calendar_name, username, password, days) tuples.
        raise_on_next: Exception to raise on next read_events(), cleared after use.
        failure_sequence: Exceptions to raise on successive read_events() calls.
    """

    def __init__(self) -> None:
        self.readings: list[list[CalendarEvent]] = [_DEFAULT_EVENTS]
        self.calls: list[tuple[str, str, str, str, int]] = []
        self.raise_on_next: Exception | None = None
        self.failure_sequence: list[Exception] = []
        self._index: int = 0

    def fail_next_reads(self, error: Exception, *, count: int) -> None:
        """Configure a finite sequence of read failures.

        Args:
            error: Exception raised by each configured failed read.
            count: Number of consecutive reads that should fail.
        """
        self.failure_sequence.extend([error] * count)

    async def read_events(
        self,
        url: str,
        calendar_name: str,
        username: str,
        password: str,
        days: int,
    ) -> list[CalendarEvent]:
        """Return the next event list from the cycle.

        Args:
            url: CalDAV server URL (recorded but not used).
            calendar_name: Calendar name (recorded but not used).
            username: Username (recorded but not used).
            password: Password (recorded but not used).
            days: Lookahead days (recorded but not used).

        Returns:
            The next list of CalendarEvent in the cycle.

        Raises:
            Exception: Whatever is set in raise_on_next, if any.
        """
        self.calls.append((url, calendar_name, username, password, days))
        if self.raise_on_next is not None:
            err = self.raise_on_next
            self.raise_on_next = None
            raise err
        if self.failure_sequence:
            raise self.failure_sequence.pop(0)
        events = self.readings[self._index % len(self.readings)]
        self._index += 1
        return events
