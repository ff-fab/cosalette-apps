"""Entry point for wiz2mqtt."""

from __future__ import annotations

from typing import Annotated

import cosalette
from cosalette.mqtt import Payload

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.adapters.wizlight import WizBulbAdapter
from wiz2mqtt.commands import to_set_state_kwargs
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.errors import error_type_map
from wiz2mqtt.models import BulbSetCommand
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

_TICK_INTERVAL_SECONDS = 5.0
"""Per-bulb poll cadence; ``get_state`` is push-cache-cheap most ticks.

Real-bulb push/heartbeat cadence is validated separately (cap-10u.19).
"""

app = cosalette.App(
    name="wiz2mqtt",
    version="0.1.0",
    description="WiZ smart bulb control over MQTT for openHAB and Home Assistant",
    settings_class=Wiz2MqttSettings,
    adapters={WizBulbPort: (WizBulbAdapter, FakeWizBulbAdapter)},
    error_type_map=error_type_map,
)


def _bulb_map(settings: cosalette.Settings) -> dict[str, BulbConfig]:
    """Map configured bulbs to per-bulb command/telemetry registrations."""
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


@app.state
def shared_state() -> SharedState:
    """State factory for per-bulb availability/publish debounce."""
    return SharedState()


@app.telemetry(
    name=_bulb_map,
    interval=_TICK_INTERVAL_SECONDS,
    publish=cosalette.OnChange(),
    summary="Per-bulb state publisher: retained state, availability debounce",
    # No state_model: the payload's keys are conditionally present (see
    # wiz2mqtt.payload.build_state_payload), which a Pydantic state_model
    # would force to null-fill on every publish rather than omit.
)
async def bulb_entity(
    ctx: cosalette.DeviceContext,
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
) -> dict[str, object] | None:
    """Per-configured-bulb telemetry: publish state, debounce availability.

    One instance is registered per ``settings.bulbs`` entry (dict-name
    ``NameSpec``, reusing ``_bulb_map`` — telemetry and command names may
    coexist, unlike device/command). See
    :func:`wiz2mqtt.entity.bulb_entity_tick` for the tick logic.
    """
    return await bulb_entity_tick(ctx, config, port, state)


def main() -> None:
    """CLI entry point."""
    app.run()


if __name__ == "__main__":
    main()
