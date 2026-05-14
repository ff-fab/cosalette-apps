"""Application composition root for velux2mqtt.

Assembles the cosalette :class:`~cosalette.App` instance, registers
configured covers through dict-name device expansion, and exposes the
CLI entry point.
"""

from __future__ import annotations

import cosalette

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


@app.device(
    name=_cover_map,
    summary="Velux cover: open/close/stop control",
)
async def cover(
    ctx: cosalette.DeviceContext,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
):
    """Run one configured Velux cover device."""
    async for event in cover_device(ctx, cover_cfg, settings):
        yield event


def main() -> None:
    """CLI entry point."""
    app.run()
