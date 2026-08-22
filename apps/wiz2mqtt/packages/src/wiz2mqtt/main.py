"""Entry point for wiz2mqtt."""

from __future__ import annotations

import cosalette

from wiz2mqtt.settings import Wiz2MqttSettings

app = cosalette.App(
    name="wiz2mqtt",
    version="0.1.0",
    description="WiZ smart bulb control over MQTT for openHAB and Home Assistant",
    settings_class=Wiz2MqttSettings,
)


def main() -> None:
    """CLI entry point."""
    app.run()


if __name__ == "__main__":
    main()
