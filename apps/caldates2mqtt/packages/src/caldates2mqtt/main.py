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

app = cosalette.App(
    name="caldates2mqtt",
    settings_class=CalDates2MqttSettings,
    adapters={
        CalDavPort: (CalDavReader, FakeCalDavReader),
    },
)


@app.on_configure
def register_devices(settings: CalDates2MqttSettings) -> None:
    """Register one device per configured calendar.

    Runs after settings resolution, before device startup.
    Replaces the eager module-level Settings() construction
    that crashed --help/--version.
    """
    for cal in settings.calendars:
        app.add_device(cal.key, make_calendar_handler(cal))


def main() -> None:
    """Start the application."""
    app.run()
