"""caldates2mqtt — CalDAV calendar dates to MQTT bridge.

Each configured CalDAV calendar becomes an independent telemetry handler
with periodic polling and on-demand re-read via MQTT trigger.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated

import cosalette
from cosalette.schema import consumer, ha_entities, ha_entity
from pydantic import ConfigDict, Field

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

    :func:`calendar` returns these instances directly; each serialises to
    ``{"title": ..., "date": ...}`` on the wire. The ``consumer()`` annotations
    describe the fields for documentation and openHAB. They yield no Home
    Assistant entity: an array item has no single value, so cosalette skips it
    (ADR-073). The supported path is the channel-level ``ha_entities()``
    composite on :class:`CalendarState`.
    """

    title: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Title"))]
    date: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Date"))]


@dataclass(frozen=True, slots=True)
class CalendarState:
    """Typed ``state_model`` for the calendar telemetry channel.

    :func:`calendar` constructs and returns an instance of this model,
    which serialises to ``{"events": [...]}`` on the wire.
    ``app.telemetry`` here is registered with a callable ``name=``
    (``_calendar_map``, keyed off user-configured ``settings.calendars``),
    the same callable-``name=`` pattern documented for velux2mqtt. A
    plain ``cosalette schema init``/``check`` would collapse every real
    per-calendar device into one channel named after this handler's
    qualname (``calendar``), but ``task caldates2mqtt:schema:generate``
    resolves settings first (``cosalette schema dump --resolve-settings``,
    ADR-051, against the checked-in ``.env.schema`` profile), expanding
    the NameSpec into real per-calendar channels (e.g. ``birthdayState``,
    ``garbageState``). See ``docs/schema.yaml`` and cap-0cg. Home Assistant
    discovery emits one event-count sensor per calendar from the composite
    below. See ``apps/caldates2mqtt/README.md`` "Home Assistant Discovery"
    section.
    """

    # ADR-057 channel-level composite: the per-property consumer() annotations on
    # CalendarEvent sit on array items, which yield no entity. This composite is
    # the supported alternative and exposes the event count per calendar.
    #
    # The event list itself stays off Home Assistant. Carrying it would need
    # json_attributes_topic, and cosalette 0.9.4 neither emits that key nor offers
    # a placeholder for a channel's generated address, so a model-level spec
    # shared by every calendar cannot name a per-calendar topic.
    __pydantic_config__ = ConfigDict(
        json_schema_extra=ha_entities(
            ha_entity(
                component="sensor",
                name="Events",
                extra={
                    "value_template": "{{ value_json.events | length }}",
                    "unit_of_measurement": "events",
                    "icon": "mdi:calendar",
                },
            )
        )
    )

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


_TRIGGER_MIN_INTERVAL_SECONDS: float = CalDates2MqttSettings.model_fields[
    "trigger_min_interval"
].default
"""Default spacing between trigger-initiated fetches (cosalette ADR-066).

Sourced from the ``trigger_min_interval`` settings field default so the two
never drift. ``caldates2mqtt/{calendar}/set`` is a public MQTT topic and each
wake is a full CalDAV round-trip against someone else's server; a stuck
automation would otherwise turn into a request flood.  A wake inside a closed
window is *held*, not dropped, so an on-demand refresh still happens — it just
waits for the window to reopen.  Enforced per calendar entity, and independent
of ``schedule=``, which continues to fire on its own cron cadence. Deployments
override it via ``CALDATES2MQTT_TRIGGER_MIN_INTERVAL``.
"""


def _resolve_trigger_min_interval(app: cosalette.App) -> float:
    """Read the configured throttle, or the default when settings are absent.

    ``min_interval=`` takes a concrete ``float`` (cosalette 0.9.1 has no
    ``setting_ref`` support for it, cap-9hn), so the value is read from the
    eagerly-built ``app.settings`` at registration time. ``app.settings``
    raises when required fields (``calendars``) are unset — as under ``--help``,
    tests, or schema generation — so fall back to the field default to keep the
    module importable in those contexts.
    """
    try:
        settings = app.settings
    except RuntimeError:
        return _TRIGGER_MIN_INTERVAL_SECONDS
    if isinstance(settings, CalDates2MqttSettings):
        return settings.trigger_min_interval
    return _TRIGGER_MIN_INTERVAL_SECONDS


@app.telemetry(
    name=_calendar_map,
    schedule=lambda cal: cal.schedule,
    triggerable=True,
    # Resolved at import time. App.__init__ eagerly builds settings, so a
    # configured deployment gets its override here; under --help/tests/schema-gen
    # (settings unavailable) it falls back to the field default (cap-9hn).
    min_interval=_resolve_trigger_min_interval(app),
    retry=3,
    retry_on=(CalDavConnectionError, CalDavTimeoutError),
    state_model=CalendarState,
)
async def calendar(
    cal: CalendarConfig,
    trigger: cosalette.TriggerPayload,
    reader: CalDavPort,
    logger: logging.Logger,
) -> CalendarState:
    """Read upcoming events from a CalDAV calendar.

    Returns a :class:`CalendarState` instance so the return annotation and
    ``state_model=`` agree (cosalette 0.9.0 ADR-068) and the wire contract
    is statically checked. The nested :class:`CalendarEvent` dataclasses
    serialise to the same ``{"title", "date"}`` dicts the handler used to
    build by hand.
    """
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

    return CalendarState(
        events=[
            CalendarEvent(title=e.title, date=e.date.isoformat())
            for e in events[:entries]
        ]
    )


def main() -> None:
    """Start the application."""
    app.run()
