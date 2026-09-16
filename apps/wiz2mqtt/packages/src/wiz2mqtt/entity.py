"""Per-bulb state-publication telemetry tick for wiz2mqtt.

Each configured bulb runs its own ``@app.telemetry`` instance (see
``main.py``), ticking :func:`bulb_entity_tick` on a fixed interval. The
framework's ``publish=OnChange()`` strategy gates the returned payload;
availability is debounced separately here, since
``ctx.mark_available``/``mark_unavailable`` never dedup on their own.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Annotated, cast

import cosalette
from cosalette import DeviceStore, EntityNotifier, Optional

from wiz2mqtt import intent, power
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
    store: Annotated[DeviceStore | None, Optional()],
    notify: EntityNotifier,
) -> dict[str, object] | None:
    """One tick of the per-bulb ``bulb_entity`` telemetry device.

    Returns the payload for the framework's ``publish=OnChange()``
    strategy to gate, or ``None`` when there is nothing to report (an
    unreachable bulb with no desired state on record yet). A bulb whose
    power source (ADR-007) declares ``when_unreachable = "no_power"`` stays
    available while unreachable; one with no power source, or a source
    declaring ``"fault"`` (the default), goes through the failure-count and
    availability path below. Either way, while the bulb cannot be read the
    payload reports its desired state (ADR-008/cap-bjw9.6), never a
    hard-coded ``OFF`` — ``powered`` (ADR-007) is what tells a consumer the
    bulb is dark.

    Also (cap-bjw9.4/cap-bjw9.5): registers the real ``firstBeat`` boot
    handler once, app-wide, on whichever bulb ticks first; resolves each
    bulb's ADR-008 phase on its own first tick; records a steady-phase
    observation as the new desired state; and recomputes the bulb's power
    source belief on every tick, arming that source's own telemetry entity.
    """
    name = config.name
    settings = cast(Wiz2MqttSettings, ctx.settings)
    power_source = settings.power_source_of(name)
    when_unreachable = power_source.when_unreachable if power_source else "fault"

    _ensure_boot_callback_registered(port, settings, state, notify)
    if name not in state.phase:
        state.phase[name] = (
            "reconnect"
            if intent.resolve_desired_state(state, store, name) is not None
            else "steady"
        )

    try:
        bulb_state = await port.get_state(config.ip)
    except WizBridgeError as exc:
        state.bulb_answered[name] = False
        belief = _recompute_and_notify(settings, state, notify, name)

        if when_unreachable == "no_power" and not isinstance(exc, WizIdentityError):
            await _mark_online_once(ctx, state, name)
            return _desired_state_payload(state, store, name, belief)

        failures = state.consecutive_failures.get(name, 0) + 1
        state.consecutive_failures[name] = min(failures, _FAILURE_THRESHOLD)
        if (
            failures >= _FAILURE_THRESHOLD
            and state.last_availability.get(name) != "offline"
        ):
            await ctx.mark_unavailable()
            state.last_availability[name] = "offline"
        return _desired_state_payload(state, store, name, belief)

    state.consecutive_failures[name] = 0
    state.bulb_answered[name] = True
    await _mark_online_once(ctx, state, name)
    if state.phase.get(name, "steady") == "steady":
        intent.record_observation(state, store, name, bulb_state, time.time())
    belief = _recompute_and_notify(settings, state, notify, name)
    return build_state_payload(bulb_state, belief)


def _desired_state_payload(
    state: SharedState,
    store: DeviceStore | None,
    name: str,
    belief: power.Belief | None,
) -> dict[str, object] | None:
    """Render the bulb's current desired state, or ``None`` if it has none yet."""
    desired = intent.resolve_desired_state(state, store, name)
    if desired is None:
        return None
    return build_state_payload(desired.as_bulb_state(), belief)


def _recompute_and_notify(
    settings: Wiz2MqttSettings, state: SharedState, notify: EntityNotifier, name: str
) -> power.Belief | None:
    """Recompute *name*'s power-source belief and arm that source's entity.

    Returns the belief for *name* itself (``None`` if it has no power
    source) so the caller can render its own ``/state`` payload without a
    second lookup. A no-op notify beyond the belief computation when *name*
    has no power source.
    """
    source = settings.power_source_of(name)
    if source is None:
        return None
    belief = power.belief_for_source(settings, state, source)
    state.source_belief[source.name] = belief
    notify(source.name)
    return belief


def _ensure_boot_callback_registered(
    port: WizBulbPort,
    settings: Wiz2MqttSettings,
    state: SharedState,
    notify: EntityNotifier,
) -> None:
    """Register the real ``firstBeat`` handler once, app-wide (cap-bjw9.4).

    Guarded by ``state.boot_callback_registered`` rather than a lifecycle
    hook: whichever configured bulb ticks first performs the one-time
    registration, since every tick already has ``port``/``state``/``notify``
    in scope.
    """
    if state.boot_callback_registered:
        return
    state.boot_callback_registered = True
    name_by_ip = {bulb.ip: bulb.name for bulb in settings.bulbs}
    port.register_boot_callback(_make_boot_handler(name_by_ip, state, notify))


def _make_boot_handler(
    name_by_ip: dict[str, str], state: SharedState, notify: EntityNotifier
) -> Callable[[str], None]:
    def _on_boot(ip: str) -> None:
        name = name_by_ip.get(ip)
        if name is None:
            return
        # Marks the return, unconfirmed (ADR-008 reconnect phase); the
        # restore itself is cap-bjw9.8, not yet implemented — this only
        # arms the entity so the next tick runs without the 60s wait, and
        # resets the failure counter since the bulb has visibly returned.
        state.phase[name] = "reconnect"
        state.consecutive_failures[name] = 0
        notify(name)

    return _on_boot


async def _mark_online_once(
    ctx: cosalette.DeviceContext, state: SharedState, name: str
) -> None:
    """Call ``mark_available`` only on the offline→online transition."""
    if state.last_availability.get(name) != "online":
        await ctx.mark_available()
        state.last_availability[name] = "online"
