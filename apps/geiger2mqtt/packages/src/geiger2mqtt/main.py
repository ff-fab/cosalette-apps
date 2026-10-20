"""Entry point for geiger2mqtt."""

from __future__ import annotations

import cosalette

from geiger2mqtt import __version__
from geiger2mqtt.settings import Geiger2MqttSettings

app = cosalette.App(
    name="geiger2mqtt",
    version=__version__,
    description="GPIO geiger counter to MQTT bridge",
    settings_class=Geiger2MqttSettings,
    # Operator opt-in GEIGER2MQTT_MQTT__ERROR_PUBLISH_VERBOSE; off by default.
    allow_error_publish_verbose=True,
)

# Runtime Home Assistant discovery for the radiation sensors.
app.discovery()


def main() -> None:
    """Start the application, or answer a CLI flag such as ``--version``.

    ``cli()`` rather than ``run()``: ``run()`` ignores the command line, so
    ``--help``, ``--version``, ``--dry-run`` and ``--env-file`` would start
    the service instead.
    """
    app.cli()


if __name__ == "__main__":
    main()
