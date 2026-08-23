"""Entry point for wiz2mqtt."""

from __future__ import annotations

from typing import Annotated

import cosalette
from cosalette.mqtt import Payload

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.adapters.wizlight import WizBulbAdapter
from wiz2mqtt.commands import to_set_state_kwargs
from wiz2mqtt.errors import error_type_map
from wiz2mqtt.models import BulbSetCommand
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings

app = cosalette.App(
    name="wiz2mqtt",
    version="0.1.0",
    description="WiZ smart bulb control over MQTT for openHAB and Home Assistant",
    settings_class=Wiz2MqttSettings,
    adapters={WizBulbPort: (WizBulbAdapter, FakeWizBulbAdapter)},
    error_type_map=error_type_map,
)


def _bulb_map(settings: cosalette.Settings) -> dict[str, BulbConfig]:
    """Map configured bulbs to per-bulb command registrations."""
    if not isinstance(settings, Wiz2MqttSettings):
        raise TypeError(f"Expected Wiz2MqttSettings, got {type(settings).__name__}")
    return {bulb.name: bulb for bulb in settings.bulbs}


@app.command(
    name=_bulb_map,
    summary="Apply a partial state update to a bulb",
    payload_model=BulbSetCommand,
)
async def bulb_set(
    cmd: Annotated[BulbSetCommand, Payload()],
    config: BulbConfig,
    port: WizBulbPort,
) -> None:
    """Handle ``wiz2mqtt/{bulb}/set``: partial update, every field optional.

    Mutual exclusion between ``color``/``color_temp``/``effect`` is
    enforced by ``BulbSetCommand``'s own validator, so a conflicting
    payload never reaches this body — the framework rejects it and
    publishes to the bulb's error topic before the handler runs.
    """
    await port.set_state(config.ip, **to_set_state_kwargs(cmd))


def main() -> None:
    """CLI entry point."""
    app.run()


if __name__ == "__main__":
    main()
