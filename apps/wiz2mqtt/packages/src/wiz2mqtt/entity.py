"""Per-bulb state-publication telemetry tick for wiz2mqtt.

Each configured bulb runs its own ``@app.telemetry`` instance (see
``main.py``), ticking :func:`bulb_entity_tick` on a fixed interval. The
framework's ``publish=OnChange()`` strategy gates the returned payload;
availability is debounced separately here, since
``ctx.mark_available``/``mark_unavailable`` never dedup on their own.
"""

from __future__ import annotations

from typing import cast

import cosalette

from wiz2mqtt.errors import WizBridgeError, WizIdentityError
from wiz2mqtt.payload import build_state_payload
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

_FAILURE_THRESHOLD = 3
"""Consecutive failed polls before a bulb is marked unavailable."""


async def bulb_entity_tick(
    ctx: cosalette.DeviceContext,
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
) -> dict[str, object] | None:
    """One tick of the per-bulb ``bulb_entity`` telemetry device.

    Returns the payload for the framework's ``publish=OnChange()``
    strategy to gate, or ``None`` to skip publishing this cycle (a
    below-threshold failure — nothing new to report while the last known
    retained state stands). A bulb whose power source (ADR-007) declares
    ``when_unreachable = "no_power"`` stays available and reports
    ``state: "OFF"`` instead of going through the failure-count/offline
    path; a bulb with no power source, or one declaring ``"fault"``
    (the default), uses the failure-count/offline path below.

    This is a placeholder equivalence to the removed bulb-level
    ``when_unreachable = "off"`` policy — it does not yet compute the
    ``powered`` belief or skip reads while a source is known off
    (cap-bjw9.7, cap-bjw9.9).
    """
    name = config.name
    settings = cast(Wiz2MqttSettings, ctx.settings)
    power_source = settings.power_source_of(name)
    when_unreachable = power_source.when_unreachable if power_source else "fault"
    try:
        bulb_state = await port.get_state(config.ip)
    except WizBridgeError as exc:
        if when_unreachable == "no_power" and not isinstance(exc, WizIdentityError):
            await _mark_online_once(ctx, state, name)
            return {"state": "OFF"}

        failures = state.consecutive_failures.get(name, 0) + 1
        state.consecutive_failures[name] = min(failures, _FAILURE_THRESHOLD)
        if (
            failures >= _FAILURE_THRESHOLD
            and state.last_availability.get(name) != "offline"
        ):
            await ctx.mark_unavailable()
            state.last_availability[name] = "offline"
        return None

    state.consecutive_failures[name] = 0
    await _mark_online_once(ctx, state, name)
    return build_state_payload(bulb_state)


async def _mark_online_once(
    ctx: cosalette.DeviceContext, state: SharedState, name: str
) -> None:
    """Call ``mark_available`` only on the offline→online transition."""
    if state.last_availability.get(name) != "online":
        await ctx.mark_available()
        state.last_availability[name] = "online"
