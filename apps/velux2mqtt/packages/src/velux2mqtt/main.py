"""Application composition root for velux2mqtt.

Assembles the cosalette :class:`~cosalette.App` instance, registers
configured covers through dict-name device expansion, and exposes the
CLI entry point.
"""

from __future__ import annotations

import cosalette

from velux2mqtt import __version__
from velux2mqtt.devices.cover import cover_device
from velux2mqtt.ports import GpioSwitchPort
from velux2mqtt.settings import CoverConfig, Velux2MqttSettings


def _cover_map(settings: cosalette.Settings) -> dict[str, CoverConfig]:
    """Map configured covers to cosalette device names."""
    if not isinstance(settings, Velux2MqttSettings):
        raise TypeError(f"Expected Velux2MqttSettings, got {type(settings).__name__}")
    return {cover.name: cover for cover in settings.covers}


app = cosalette.App(
    name="velux2mqtt",
    version=__version__,
    description="Velux cover control via KLF 050 remotes and GPIO",
    settings_class=Velux2MqttSettings,
    restart_after_failures=5,
    max_restarts=3,
    adapters={
        GpioSwitchPort: (
            "velux2mqtt.adapters.gpiozero_adapter:GpiozeroAdapter",
            "velux2mqtt.adapters.fake:FakeGpio",
        ),
    },
)

app.device(
    name=_cover_map,
    summary="Velux cover: GPIO-driven open/close/stop/position control",
    behavior=[
        "Startup homing to a known endpoint for reliable position reference",
        "Open/close/stop commands via GPIO button presses on KLF 050 remote",
        "Position targeting (0\u2013100%) with time-based position tracking",
        "Calibration sub-entity (start/go/mark/cancel phases)",
        "Drift compensation: periodic re-homing after consecutive intermediate moves",
    ],
    effects=[
        "Presses GPIO pins (up/stop/down) via GpioSwitchPort",
        "Publishes cover position state to MQTT",
    ],
)(cover_device)


def main() -> None:
    """CLI entry point."""
    app.run()
