"""Application composition root for velux2mqtt.

Assembles the cosalette :class:`~cosalette.App` instance, registers
one device per configured cover (e.g. blind, window), and exposes the
CLI entry point.
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


@app.on_configure
def register_covers(settings: Velux2MqttSettings) -> None:
    """Register one device per configured cover (deferred until settings resolved)."""
    for cover_cfg in settings.covers:
        app.add_device(
            cover_cfg.name,
            make_cover(cover_cfg, settings),
            summary=f"Velux cover {cover_cfg.name}: open/close/stop control",
        )


def main() -> None:
    """CLI entry point."""
    app.run()
