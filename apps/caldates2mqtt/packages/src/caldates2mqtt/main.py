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
from caldates2mqtt.settings import (
    DAYS_MAX,
    ENTRIES_MAX,
    CalDates2MqttSettings,
    CalendarConfig,
)

# Titles come from someone else's CalDAV server and have no length limit.
TITLE_MAX = 100


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One upcoming event entry within a calendar's event list.

    :func:`calendar` returns these instances directly; each serialises to
    ``{"title": ..., "date": ...}`` on the wire. The ``consumer()`` annotations
    describe the fields for documentation only. They yield no discovery entity
    on either target: an array item has no single value, so cosalette skips it
    (cosalette ADR-073). :class:`CalendarState` covers both targets instead:
    Home Assistant through its ``ha_entities()`` composite, openHAB through the
    ``count`` aggregate on ``events``.
    """

    title: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Title"))]
    date: Annotated[str, Field(json_schema_extra=consumer(display_name="Event Date"))]


# cosalette ADR-057 channel-level composite: the per-property consumer() annotations
# on CalendarEvent sit on array items, which yield no entity. This composite is the
# supported alternative. It exposes the event count as the entity state and the
# event list as Home Assistant attributes.
#
# json_attributes_template carries the list. cosalette 0.9.5 defaults
# json_attributes_topic to the channel's own resolved state topic (ADR-075), so this
# one model-level spec names each calendar's own topic. Home Assistant requires the
# template to yield a JSON object, not a bare array, so it wraps the list as
# {"events": [...]}. It names the key instead of passing value_json through, so a
# field added to CalendarState later does not become an attribute by accident.
#
# Home Assistant's recorder drops attributes above 16384 bytes. Each event costs
# about 33 bytes plus the UTF-8 length of its title. With entries <= ENTRIES_MAX and
# titles <= TITLE_MAX characters, the worst case is about 6.7 kB for ASCII titles and
# 11.7 kB for two-byte characters such as umlauts. Only full-length titles made of
# three- or four-byte characters (CJK, emoji) can pass the cap. The default of 5
# entries produces about 400 bytes.
_EVENT_COUNT_SENSOR = ha_entities(
    ha_entity(
        component="sensor",
        name="Events",
        extra={
            "value_template": "{{ value_json.events | length }}",
            "json_attributes_template": "{{ {'events': value_json.events} | tojson }}",
            "unit_of_measurement": "events",
            "state_class": "measurement",
            "icon": "mdi:calendar",
        },
    )
)


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
    ``garbageState``). See ``docs/schema.yaml``. Home Assistant
    discovery emits one event-count sensor per calendar from the
    :data:`_EVENT_COUNT_SENSOR` composite above; that sensor also carries the
    calendar's event list as attributes. See
    ``apps/caldates2mqtt/README.md`` "Home Assistant Discovery" section.
    """

    __pydantic_config__ = ConfigDict(json_schema_extra=_EVENT_COUNT_SENSOR)

    # cosalette ADR-076 typed aggregate: gives the array one value, for openHAB.
    # Home Assistant never reads it: the composite above replaces per-property
    # generation, so HA keeps exactly one sensor per calendar.
    events: Annotated[
        list[CalendarEvent],
        Field(
            json_schema_extra=consumer(
                display_name="Upcoming Events", unit="events", aggregate="count"
            )
        ),
    ]


app = cosalette.App(
    name="caldates2mqtt",
    version=__version__,
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
    error_type_map=error_type_map,
)

# ADR-004: runtime HA discovery, generated from the live per-calendar registry.
app.discovery()


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

    ``min_interval=`` takes a concrete ``float`` without ``setting_ref``
    support, so the value is read from the
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
    # (settings unavailable) it falls back to the field default.
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
            entries = min(raw_entries, ENTRIES_MAX)
        raw_days = trigger.get("days", None)
        if isinstance(raw_days, int) and raw_days > 0:
            days = min(raw_days, DAYS_MAX)
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
            CalendarEvent(title=e.title[:TITLE_MAX], date=e.date.isoformat())
            for e in events[:entries]
        ]
    )


def main() -> None:
    """Start the application."""
    app.run()
