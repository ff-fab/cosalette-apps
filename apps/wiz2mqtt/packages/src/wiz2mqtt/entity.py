"""Per-bulb state-publication telemetry tick for wiz2mqtt.

Each configured bulb runs its own ``@app.telemetry`` instance (see
``main.py``), ticking :func:`bulb_entity_tick` on a fixed interval. The
framework's ``publish=OnChange()`` strategy gates the returned payload;
availability is debounced separately here, since
``ctx.mark_available``/``mark_unavailable`` never dedup on their own.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from collections.abc import Callable
from typing import Annotated, cast

import cosalette
from cosalette import DeviceStore, EntityNotifier, Optional

from wiz2mqtt import intent, power
from wiz2mqtt.colour import clamp_kelvin
from wiz2mqtt.commands import SetStateKwargs
from wiz2mqtt.errors import WizBridgeError, WizIdentityError
from wiz2mqtt.models import BulbCapabilities, BulbState
from wiz2mqtt.payload import build_state_payload
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

logger = logging.getLogger(__name__)

_FAILURE_THRESHOLD = 3
"""Consecutive failed polls before a bulb is marked unavailable."""

_MAX_WRITE_ATTEMPTS = 3
"""ADR-008: a return-path write gets three total write-and-read-back
attempts, including the first — not three retries after it (2026-09-14
corrective amendment)."""

_HUE_TOLERANCE = 1.0
_SATURATION_TOLERANCE = 1.0
"""Read-back comparison tolerance, in the same hue (0..360) / saturation
(0..100) units :class:`~wiz2mqtt.models.BulbState` uses. A WiZ bulb derives
hue/saturation from an RGB byte round-trip (see :mod:`wiz2mqtt.colour`), so
the value read back after a colour write is not always bit-identical to the
value sent."""


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
    unreachable bulb with no desired state on record yet). Availability
    means fault only (ADR-007/cap-bjw9.9): once the bulb has failed the
    threshold and its power source belief is ``"off"``, the network read
    is skipped entirely — no ``port.get_state`` call, no failure-counter
    advance — and the bulb stays available, reporting its desired state
    with ``powered = false``.
    A bulb whose belief is ``"on"`` or ``"unknown"`` (no power source, or a
    peer still answering) goes through the normal failure-count and
    availability path below, so a genuinely unreachable bulb on a live
    circuit still goes offline. Either way, while the bulb cannot be read
    the payload reports its desired state (ADR-008/cap-bjw9.6), never a
    hard-coded ``OFF`` — ``powered`` (ADR-007) is what tells a consumer the
    bulb is dark.

    Also (cap-bjw9.4/cap-bjw9.5/cap-bjw9.8): registers the real ``firstBeat``
    boot handler once, app-wide, on whichever bulb ticks first; resolves
    each bulb's ADR-008 phase on its own first tick; records a steady-phase
    observation as the new desired state; runs the ADR-008 return path
    exactly once per return to reachability, from this tick and never from
    the push callback, when the phase is ``"reconnect"``; and recomputes
    the bulb's power source belief on every tick, arming that source's own
    telemetry entity.
    """
    name = config.name
    settings = cast(Wiz2MqttSettings, ctx.settings)

    _ensure_boot_callback_registered(port, settings, state, notify)
    if name not in state.phase:
        state.phase[name] = (
            "reconnect"
            if intent.resolve_desired_state(state, store, name) is not None
            else "steady"
        )

    # Skip the read while the source is known off (ADR-007/cap-bjw9.9): an
    # absent bulb otherwise holds pywizlight's asyncio.Lock for the full
    # 13 s TIMEOUT per cycle. See _should_skip_read for the two bypasses.
    belief = power.belief_for_bulb(settings, state, name)
    if _should_skip_read(state, name, belief):
        await _mark_online_once(ctx, state, name)
        return _desired_state_payload(state, store, name, belief)

    observation_generation = state.desired_state_generation.get(name, 0)
    try:
        bulb_state = await port.get_state(config.ip)
    except WizBridgeError as exc:
        failures = state.consecutive_failures.get(name, 0) + 1
        failures = min(failures, _FAILURE_THRESHOLD)
        state.consecutive_failures[name] = failures
        if failures >= _FAILURE_THRESHOLD:
            state.bulb_answered[name] = False
        else:
            state.bulb_answered.setdefault(name, False)
        belief = _recompute_and_notify(settings, state, notify, name)

        if belief == "off" and not isinstance(exc, WizIdentityError):
            await _mark_online_once(ctx, state, name)
            return _desired_state_payload(state, store, name, belief)

        if (
            failures >= _FAILURE_THRESHOLD
            and state.last_availability.get(name) != "offline"
        ):
            await ctx.mark_unavailable()
            state.last_availability[name] = "offline"
        return _desired_state_payload(state, store, name, belief)

    was_unreachable = state.bulb_answered.get(name) is False
    state.consecutive_failures[name] = 0
    state.bulb_answered[name] = True
    await _mark_online_once(ctx, state, name)
    # Arm reconnect on slow polling recovery: the boot callback handles the
    # fast path, but a successful read after the failure threshold (without a
    # boot event) also needs to run the return path when a desired state exists.
    if (
        was_unreachable
        and state.phase.get(name) == "steady"
        and intent.resolve_desired_state(state, store, name) is not None
    ):
        state.phase[name] = "reconnect"
    if state.phase.get(name, "steady") == "reconnect":
        try:
            return await _run_return_path(
                ctx, config, port, state, store, settings, notify, name, bulb_state
            )
        except WizBridgeError:
            state.phase[name] = "steady"
            belief = _recompute_and_notify(settings, state, notify, name)
            return build_state_payload(bulb_state, belief)
    if state.desired_state_generation.get(name, 0) == observation_generation:
        intent.record_observation(state, store, name, bulb_state, time.time())
    belief = _recompute_and_notify(settings, state, notify, name)
    return build_state_payload(bulb_state, belief)


def _should_skip_read(
    state: SharedState, name: str, belief: power.Belief | None
) -> bool:
    """Whether *name*'s tick should skip ``port.get_state`` this cycle (cap-bjw9.9).

    Two conditions must both hold: the belief is ``"off"``, and *name* has
    failed ``_FAILURE_THRESHOLD`` polls in a row. ADR-007 skips reads "after
    the threshold", so a single transient timeout on a live bulb (which
    already yields the tie-break belief ``"off"`` on a ``no_power`` source,
    see ``power.compute_belief``) does not latch the bulb dark: it keeps
    being read until the evidence is firm.

    The "reconnect" phase bypasses the skip too — set by the boot callback
    (``_make_boot_handler``) reacting to the bulb's own firstBeat broadcast,
    which arrives independently of whether this tick polls, so this is what
    lets the belief leave "off" again once evidence does exist.
    """
    return (
        belief == "off"
        and state.consecutive_failures.get(name, 0) >= _FAILURE_THRESHOLD
        and state.phase.get(name) != "reconnect"
    )


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


async def _run_return_path(
    ctx: cosalette.DeviceContext,
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
    store: DeviceStore | None,
    settings: Wiz2MqttSettings,
    notify: EntityNotifier,
    name: str,
    bulb_state: BulbState,
) -> dict[str, object] | None:
    """Run the ADR-008 return path once for *name* (cap-bjw9.8).

    Called only from :func:`bulb_entity_tick`'s success path, never from
    the push callback (:func:`_make_boot_handler` only arms the phase).
    Exactly one branch of the three-way rule applies, per the 2026-09-14
    corrective amendment: a non-expired pending command always wins; else
    the stored desired state restores only when ``restore_previous_state``
    is set *and* a record exists; otherwise *bulb_state* — the report that
    detected this return — becomes the new desired state and the phase
    settles to steady without touching the wire.

    A write is read back and retried up to three attempts total
    (:func:`_write_and_verify`). On success the pending command or stored
    desired state applied is already what ``state.desired_state`` holds
    (recorded when the command was issued/stored), so nothing more needs
    writing. On exhaustion, a structured error is published to
    ``wiz2mqtt/{bulb}/error``, authority hands back to the lamp (the last
    observed state becomes the new desired state), and the phase still
    settles to steady — ADR-008 does not retry a return path across ticks.

    The write-and-verify loop invalidates the adapter's cache before each
    read-back so the comparison is always against an authoritative poll,
    never the optimistic merge ``set_state`` applied. Transport errors
    during the loop count as failed attempts; on exhaustion the fallback
    (the state that triggered this return) is used for the error publish.

    If a new pending command arrived during the loop (a command enqueued
    while the bulb was being written to), the phase stays ``"reconnect"``
    so the next tick processes it instead of settling to steady.
    """
    now = time.time()
    kwargs = intent.pop_valid(
        state.pending_commands, name, settings.queued_command_ttl, now
    )
    if kwargs is None and config.restore_previous_state:
        desired = intent.resolve_desired_state(state, store, name)
        if desired is not None:
            kwargs = intent.desired_state_to_set_state_kwargs(desired)

    if kwargs is None:
        observed = bulb_state
        intent.record_observation(state, store, name, observed, now)
    else:
        observed, attempts, confirmed = await _write_and_verify(
            port, config.ip, kwargs, bulb_state
        )
        if not confirmed:
            logger.warning(
                "Bulb %s: return-path restore unconfirmed after %d attempts; "
                "handing authority back to the lamp",
                name,
                attempts,
            )
            await ctx.publish(
                "error",
                json.dumps(
                    {"attempts": attempts, "state": dataclasses.asdict(observed)}
                ),
            )
            intent.record_observation(state, store, name, observed, now)

    if name not in state.pending_commands:
        state.phase[name] = "steady"
    belief = _recompute_and_notify(settings, state, notify, name)
    return build_state_payload(observed, belief)


async def _write_and_verify(
    port: WizBulbPort, ip: str, kwargs: SetStateKwargs, fallback: BulbState
) -> tuple[BulbState, int, bool]:
    """Write *kwargs*, read back, retry until it matches or attempts run out.

    Returns the last-observed state, the attempt count used (1-3), and
    whether that last read-back confirmed the write. Transport errors
    (``WizBridgeError``) count as failed attempts; on exhaustion the
    *fallback* state is returned so the caller's error handler has
    something to publish.  The adapter's cache is invalidated before each
    read-back so the comparison sees an authoritative poll, not the
    optimistic merge ``set_state`` applied.
    """
    caps = await port.get_capabilities(ip)
    last_observed = fallback
    for attempt in range(1, _MAX_WRITE_ATTEMPTS + 1):
        try:
            await port.set_state(ip, **kwargs)
            port.invalidate_cache(ip)
            observed = await port.get_state(ip)
        except WizBridgeError:
            if attempt == _MAX_WRITE_ATTEMPTS:
                return last_observed, attempt, False
            continue
        last_observed = observed
        confirmed = _kwargs_match_observed(kwargs, observed, caps)
        if confirmed or attempt == _MAX_WRITE_ATTEMPTS:
            return observed, attempt, confirmed
    raise AssertionError("unreachable: _MAX_WRITE_ATTEMPTS >= 1")


def _kwargs_match_observed(
    kwargs: SetStateKwargs,
    observed: BulbState,
    caps: BulbCapabilities | None = None,
) -> bool:
    """Whether *observed* confirms the write *kwargs* described.

    Desired OFF only checks the on/off bit, since no appearance was sent.
    Desired ON checks on/off plus every appearance field the write actually
    carried — a field the caller left ``None`` (a partial pending command
    that never touched it) is not checked. Hue uses circular distance
    (0..360 wraps), and colour temperature is clamped to the bulb's range
    before comparison, matching the adapter's own clamping in ``set_state``.
    """
    if kwargs.get("state") is False:
        return observed.state is False
    if kwargs.get("state") is True and observed.state is not True:
        return False
    for field in ("brightness", "scene"):
        expected = kwargs.get(field)
        if expected is not None and getattr(observed, field) != expected:
            return False
    expected_ct = kwargs.get("color_temp_kelvin")
    if expected_ct is not None:
        if caps is not None:
            expected_ct = clamp_kelvin(expected_ct, caps)
        if observed.color_temp_kelvin != expected_ct:
            return False
    speed = kwargs.get("speed")
    if speed is not None and observed.effect_speed != speed:
        return False
    hue_expected = kwargs.get("hue")
    if hue_expected is not None:
        hue_actual = observed.hue
        if hue_actual is None:
            return False
        diff = abs(hue_actual - hue_expected)
        if min(diff, 360.0 - diff) > _HUE_TOLERANCE:
            return False
    sat_expected = kwargs.get("saturation")
    if sat_expected is not None:
        sat_actual = observed.saturation
        if sat_actual is None or abs(sat_actual - sat_expected) > _SATURATION_TOLERANCE:
            return False
    return True


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
        # Marks the return, unconfirmed (ADR-008 reconnect phase). The
        # restore itself (cap-bjw9.8) runs from the next entity tick, never
        # from here — this only arms the entity so that tick runs without
        # the 60s wait, and resets the failure counter since the bulb has
        # visibly returned.
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
