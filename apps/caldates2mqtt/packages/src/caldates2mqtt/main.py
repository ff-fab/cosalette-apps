"""caldates2mqtt — CalDAV calendar dates to MQTT bridge.

Each configured CalDAV calendar becomes an independent telemetry handler
with periodic polling and on-demand re-read via MQTT trigger.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cosalette

from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.ports import CalDavPort
from caldates2mqtt.settings import CalDates2MqttSettings

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from typing import Any

    from caldates2mqtt.settings import CalendarConfig

_ENTRIES_MAX = 50
_DAYS_MAX = 365

app = cosalette.App(
    name="caldates2mqtt",
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
)


def make_calendar_handler(
    cal: CalendarConfig,
) -> Callable[..., Coroutine[Any, Any, dict[str, object]]]:
    """Create a telemetry handler for a single calendar.

    Args:
        cal: Calendar configuration captured in the closure.

    Returns:
        Async telemetry handler for use with app.add_telemetry().
    """

    async def calendar_handler(
        trigger: cosalette.TriggerPayload,
        reader: CalDavPort,
        logger: logging.Logger,
    ) -> dict[str, object]:
        """Read upcoming events from a CalDAV calendar."""
        entries = cal.entries
        days = cal.days

        if trigger.is_triggered:
            raw_entries = trigger.get("entries", None)
            if isinstance(raw_entries, int) and raw_entries > 0:
                entries = min(raw_entries, _ENTRIES_MAX)
            raw_days = trigger.get("days", None)
            if isinstance(raw_days, int) and raw_days > 0:
                days = min(raw_days, _DAYS_MAX)
            logger.info("Re-read triggered for calendar %s", cal.key)
        else:
            logger.debug("Reading calendar %s", cal.key)

        events = await reader.read_events(
            url=cal.url,
            calendar_name=cal.calendar_name,
            username=cal.username,
            password=cal.password.get_secret_value(),
            days=days,
        )

        return {
            "events": [
                {"title": e.title, "date": e.date.isoformat()} for e in events[:entries]
            ]
        }

    return calendar_handler


@app.on_configure
def setup_calendars(settings: CalDates2MqttSettings) -> None:
    """Register one telemetry handler per configured calendar."""
    for cal in settings.calendars:
        app.add_telemetry(
            cal.key,
            make_calendar_handler(cal),
            interval=cal.poll_interval,
            triggerable=True,
        )


def main() -> None:
    """Start the application."""
    app.run()
