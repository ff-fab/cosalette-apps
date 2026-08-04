"""caldates2mqtt — CalDAV calendar dates to MQTT bridge.

Each configured CalDAV calendar becomes an independent telemetry handler
with periodic polling and on-demand re-read via MQTT trigger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import cosalette
from cosalette.schema import consumer
from pydantic import Field

from caldates2mqtt import __version__
from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import (
    CalDavConnectionError,
    CalDavTimeoutError,
    error_type_map,
)
from caldates2mqtt.ports import CalDavPort
from caldates2mqtt.settings import CalDates2MqttSettings, CalendarConfig

_ENTRIES_MAX = 50
_DAYS_MAX = 365


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One upcoming event entry within a calendar's event list.

    Mirrors the per-event dict built by :func:`calendar`:
    ``{"title": ..., "date": ...}``. The ``consumer()`` annotations are
    preparatory only: cosalette's HA/OpenHAB generators walk a channel's
    *top-level* properties, never nested list items, so these are inert
    today — no discovery payload results. They're wired now so this model
    is ready the moment the schema pipeline gains list/array payload
    support (tracked upstream).
    """

    title: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Title"))]
    date: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Date"))]


@dataclass(frozen=True, slots=True)
class CalendarState:
    """Typed ``state_model`` for the calendar telemetry channel.

    Mirrors the dict returned by :func:`calendar`: ``{"events": [...]}``.
    Wiring this (instead of leaving the channel ``additionalProperties:
    true``) also doesn't yet produce HA discovery: ``app.telemetry`` here
    is registered with a callable ``name=`` (``_calendar_map``, keyed off
    user-configured ``settings.calendars``), so cosalette's static schema
    pipeline collapses every real per-calendar device into one channel
    named after this handler's qualname (``calendar``) — the same
    callable-``name=`` limitation documented for velux2mqtt. Both blockers
    (list payloads, qualname collapse) need the upstream settings-aware
    schema pipeline before HA discovery becomes functional here. See
    ``apps/caldates2mqtt/README.md`` "Home Assistant Discovery" section.
    """

    events: list[CalendarEvent]


app = cosalette.App(
    name="caldates2mqtt",
    version=__version__,
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
    error_type_map=error_type_map,
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
    state_model=CalendarState,
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
