"""caldates2mqtt application entry point.

Wires the cosalette App with calendar devices, CalDAV adapter,
and settings. One device per configured calendar, registered
imperatively from settings.
"""

from __future__ import annotations

import cosalette

from caldates2mqtt.adapters.caldav_reader import CalDavReader
from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.devices.calendar import make_calendar_handler
from caldates2mqtt.ports import CalDavPort
from caldates2mqtt.settings import CalDates2MqttSettings

# Eagerly construct settings so device registration can iterate calendars.
# This means --help/--version will crash if required env vars are absent.
_settings = CalDates2MqttSettings()  # type: ignore[call-arg]

app = cosalette.App(
    name="caldates2mqtt",
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
)

# Dynamic device registration — one device per configured calendar.
for _cal in _settings.calendars:
    app.add_device(_cal.key, make_calendar_handler(_cal))


def main() -> None:
    """Start the application."""
    app.run()
