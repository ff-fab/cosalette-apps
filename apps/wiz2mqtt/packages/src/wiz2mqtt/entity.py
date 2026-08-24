"""Per-bulb state-publication telemetry tick for wiz2mqtt (cap-10u.13).

Each configured bulb runs its own ``@app.telemetry`` instance (see
``main.py``), ticking :func:`bulb_entity_tick` on a fixed interval. The
framework's ``publish=OnChange()`` strategy gates the returned payload;
availability is debounced separately here, since
``ctx.mark_available``/``mark_unavailable`` never dedup on their own.
"""

from __future__ import annotations

import cosalette

from wiz2mqtt.errors import WizBridgeError
from wiz2mqtt.payload import build_state_payload
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig
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
    retained state stands). Bulbs configured with ``when_unreachable =
    "off"`` stay available and report ``state: "OFF"`` instead of going
    through the failure-count/offline path.
    """
    name = config.name
    try:
        bulb_state = await port.get_state(config.ip)
    except WizBridgeError:
        if config.when_unreachable == "off":
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
