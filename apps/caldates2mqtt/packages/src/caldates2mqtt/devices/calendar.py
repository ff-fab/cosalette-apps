"""Calendar telemetry handler for caldates2mqtt.

Each configured CalDAV calendar becomes an independent telemetry source with
periodic polling handled by the framework. No command support.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from caldates2mqtt.ports import CalDavPort

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from caldates2mqtt.settings import CalendarConfig


def make_calendar_telemetry(
    cal: CalendarConfig,
) -> Callable[[CalDavPort], Awaitable[dict[str, object]]]:
    """Create a telemetry handler for a single calendar.

    Args:
        cal: Calendar configuration captured in the closure.

    Returns:
        Async telemetry function for use with app.telemetry().
    """

    async def read_calendar(reader: CalDavPort) -> dict[str, object]:
        """Read events from CalDAV and return as state dict."""
        events = await reader.read_events(
            url=cal.url,
            calendar_name=cal.calendar_name,
            username=cal.username,
            password=cal.password.get_secret_value(),
            days=cal.days,
        )
        sliced = events[: cal.entries]
        return {
            "events": [{"title": e.title, "date": e.date.isoformat()} for e in sliced]
        }

    return read_calendar
