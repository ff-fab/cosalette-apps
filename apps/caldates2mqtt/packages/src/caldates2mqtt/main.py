"""caldates2mqtt — CalDAV calendar dates to MQTT bridge.

Each configured CalDAV calendar becomes an independent telemetry handler
with periodic polling and on-demand re-read via MQTT trigger.
"""

from __future__ import annotations

import logging

import cosalette

from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import CalDavConnectionError, CalDavTimeoutError
from caldates2mqtt.ports import CalDavPort
from caldates2mqtt.settings import CalDates2MqttSettings, CalendarConfig

_ENTRIES_MAX = 50
_DAYS_MAX = 365

app = cosalette.App(
    name="caldates2mqtt",
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
)


def _calendar_map(s: cosalette.Settings) -> dict[str, CalendarConfig]:
    if not isinstance(s, CalDates2MqttSettings):
        raise TypeError(f"Expected CalDates2MqttSettings, got {type(s).__name__}")
    return {cal.key: cal for cal in s.calendars}


@app.telemetry(
    name=_calendar_map,
    schedule=lambda cal: cal.schedule,
    triggerable=True,
    retry=3,
    retry_on=(CalDavConnectionError, CalDavTimeoutError),
)
async def calendar(
    cal: CalendarConfig,
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


def main() -> None:
    """Start the application."""
    app.run()
