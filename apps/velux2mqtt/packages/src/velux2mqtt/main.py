"""Application composition root for velux2mqtt.

Assembles the cosalette :class:`~cosalette.App` instance, registers
one device per configured cover, and exposes the CLI entry point.
"""

from __future__ import annotations

import cosalette

from velux2mqtt.devices.cover import make_cover
from velux2mqtt.ports import GpioSwitchPort
from velux2mqtt.settings import Velux2MqttSettings

app = cosalette.App(
    name="velux2mqtt",
    version="0.0.0",
    description="Velux cover control via KLF 050 remotes and GPIO",
    settings_class=Velux2MqttSettings,
    adapters={
        GpioSwitchPort: (
            "velux2mqtt.adapters.gpiozero_adapter:GpiozeroAdapter",
            "velux2mqtt.adapters.fake:FakeGpio",
        ),
    },
)

# Register one device per cover from settings.
# Settings are read eagerly here so cover devices are registered at
# import time — cosalette needs registrations before run().
_settings = Velux2MqttSettings()

for _cover_cfg in _settings.covers:
    app.add_device(_cover_cfg.name, make_cover(_cover_cfg, _settings))


def main() -> None:
    """CLI entry point."""
    app.run()
