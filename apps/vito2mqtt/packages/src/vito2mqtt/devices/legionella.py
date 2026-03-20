# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Legionella treatment feature — schedule check & async device state machine.

This module provides:

- ``TIMER_SIGNAL_FOR_DAY``: Maps ``datetime.weekday()`` values to the
  corresponding hot-water timer signal names in the command registry.
- ``is_within_heating_window``: Checks whether a given time falls within
  an active heating schedule slot with sufficient remaining margin.
- ``_legionella_device``: Async device function implementing the treatment
  state machine (idle → checking → heating → restoring → idle).
- ``register_legionella``: Imperatively registers the device on an
  :class:`~cosalette.App` instance.

References:
    ADR-007 — Telemetry Coalescing Groups
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, time, timedelta

from cosalette import App, DeviceContext, DeviceStore

from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.optolink.codec import CycleTimeSchedule
from vito2mqtt.ports import OptolinkPort

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Day-to-signal mapping
# ---------------------------------------------------------------------------

TIMER_SIGNAL_FOR_DAY: dict[int, str] = {
    0: "timer_hw_monday",
    1: "timer_hw_tuesday",
    2: "timer_hw_wednesday",
    3: "timer_hw_thursday",
    4: "timer_hw_friday",
    5: "timer_hw_saturday",
    6: "timer_hw_sunday",
}
"""Maps ``datetime.weekday()`` (0=Monday … 6=Sunday) to signal names."""

LEGIONELLA_SETPOINT_SIGNAL = "hot_water_setpoint"
"""Signal name used to read/write the hot-water setpoint temperature."""

_STORE_KEY_ORIGINAL_SETPOINT = "original_setpoint"
_STORE_KEY_ACTIVE = "active"

# ---------------------------------------------------------------------------
# Heating window check
# ---------------------------------------------------------------------------


def is_within_heating_window(
    schedule: CycleTimeSchedule,
    now: time,
    safety_margin_minutes: int = 30,
) -> bool:
    """Check whether *now* falls within any active time slot in *schedule*.

    A slot matches when ``start <= now`` **and** the remaining time before
    the slot ends is **strictly greater** than *safety_margin_minutes*.

    .. note:: Overnight windows (``end < start``) are not supported and
       will never match.  Boiler timer programs do not span midnight.

    Parameters:
        schedule: Decoded cycle-time schedule — a list of up to 4
            ``[[start_h, start_m], [end_h, end_m]]`` pairs.  Slots whose
            hours/minutes contain ``None`` are treated as inactive.
        now: Current time of day to test.
        safety_margin_minutes: Minimum number of full minutes that must
            remain before the slot ends for the check to pass.  Must be
            non-negative.

    Returns:
        ``True`` if any active slot satisfies the condition, ``False``
        otherwise.

    Raises:
        ValueError: If *safety_margin_minutes* is negative.
    """
    if safety_margin_minutes < 0:
        msg = f"safety_margin_minutes must be non-negative, got {safety_margin_minutes}"
        raise ValueError(msg)
    for pair in schedule:
        start_slot, end_slot = pair

        # Skip inactive ("not set") slots
        if None in start_slot or None in end_slot:
            continue

        # At this point all values are confirmed int — narrow for mypy
        start_h: int = start_slot[0]  # type: ignore[assignment]
        start_m: int = start_slot[1]  # type: ignore[assignment]
        end_h: int = end_slot[0]  # type: ignore[assignment]
        end_m: int = end_slot[1]  # type: ignore[assignment]

        slot_start = time(start_h, start_m)

        # Compute the effective end by subtracting the safety margin.
        # We use timedelta arithmetic through a datetime anchor to avoid
        # negative-time edge cases.
        _anchor = timedelta(hours=end_h, minutes=end_m)
        _margin = timedelta(minutes=safety_margin_minutes)
        effective_end_td = _anchor - _margin

        # If the margin exceeds the end time the effective end wraps
        # negative — no useful window remains.
        if effective_end_td.total_seconds() < 0:
            continue

        total_seconds = int(effective_end_td.total_seconds())
        effective_end = time(total_seconds // 3600, (total_seconds % 3600) // 60)

        if slot_start <= now < effective_end:
            return True

    return False


# ---------------------------------------------------------------------------
# Async device state machine
# ---------------------------------------------------------------------------


async def _legionella_device(ctx: DeviceContext, store: DeviceStore) -> None:
    """Legionella treatment device loop.

    Runs as a long-lived concurrent task managed by the cosalette framework.
    Waits for ``{"action": "start"}`` commands on ``legionella/set``, then
    performs a safety-checked hot-water setpoint boost for a configurable
    duration.

    The lifecycle:

    1. **Startup recovery** — if a previous run was interrupted mid-treatment,
       the original setpoint is restored from the :class:`DeviceStore`.
    2. **Idle** — sleeps until a command arrives via MQTT.
    3. **Checking** — reads today's timer schedule and verifies the heating
       window has enough remaining time.
    4. **Heating** — boosts the setpoint and counts down minute-by-minute.
    5. **Restoring** — writes the original setpoint back and clears state.

    Parameters:
        ctx: Per-device runtime context (injected by framework).
        store: Per-device persistent store (injected by framework).
    """
    port = ctx.adapter(OptolinkPort)  # type: ignore[type-abstract]
    settings: Vito2MqttSettings = ctx.settings  # type: ignore[assignment]

    # -- Queue for command → loop communication -----------------------------
    command_queue: asyncio.Queue[str] = asyncio.Queue()

    @ctx.on_command
    async def _handle_command(topic: str, payload: str) -> None:  # noqa: ARG001
        """Parse incoming MQTT command and enqueue it for the main loop."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed JSON on %s: %s", topic, payload)
            return

        if not isinstance(data, dict):
            logger.warning("Ignoring non-object JSON on %s: %s", topic, payload)
            return

        action = data.get("action")
        if action not in {"start", "cancel"}:
            logger.warning("Unknown legionella action: %r", action)
            return

        await command_queue.put(action)

    # -- Startup recovery ---------------------------------------------------
    if store.get(_STORE_KEY_ACTIVE):
        original = store.get(_STORE_KEY_ORIGINAL_SETPOINT)
        logger.info(
            "Recovering from interrupted treatment — restoring setpoint to %s",
            original,
        )
        if original is not None:
            await port.write_signal(LEGIONELLA_SETPOINT_SIGNAL, original)
        store.update({_STORE_KEY_ACTIVE: False, _STORE_KEY_ORIGINAL_SETPOINT: None})
        store.save()
        await ctx.publish_state({"status": "recovered", "original_setpoint": original})

    # -- Publish initial idle state -----------------------------------------
    await ctx.publish_state({"status": "idle"})

    # -- Main loop ----------------------------------------------------------
    while not ctx.shutdown_requested:
        # Wait for a command (wake every 5 s to check shutdown)
        try:
            action = await asyncio.wait_for(command_queue.get(), timeout=5)
        except TimeoutError:
            continue

        if action == "start":
            await _handle_start(
                ctx,
                store,
                port,
                settings,
                command_queue,
            )
        # "cancel" while idle is a no-op


async def _heating_countdown(
    ctx: DeviceContext,
    command_queue: asyncio.Queue[str],
    target_temp: object,
    original_setpoint: object,
    remaining_minutes: int,
) -> None:
    """Count down minute-by-minute, publishing heating state updates.

    Exits early if the device shuts down or a ``cancel`` command arrives
    via *command_queue*.  Uses ``asyncio.wait_for`` on the queue so that
    cancel commands are acted on immediately rather than waiting for the
    next 60-second tick.
    """
    while remaining_minutes > 0 and not ctx.shutdown_requested:
        # Wait 60 s for a command; timeout means "one minute elapsed"
        try:
            action = await asyncio.wait_for(command_queue.get(), timeout=60)
        except TimeoutError:
            action = None

        # Check for cancel
        if action == "cancel":
            logger.info("Legionella treatment cancelled")
            break

        remaining_minutes -= 1
        if remaining_minutes > 0 and not ctx.shutdown_requested:
            await ctx.publish_state(
                {
                    "status": "heating",
                    "target_temperature": target_temp,
                    "original_setpoint": original_setpoint,
                    "remaining_minutes": remaining_minutes,
                }
            )


async def _restore_setpoint(
    ctx: DeviceContext,
    store: DeviceStore,
    port: OptolinkPort,
    original_setpoint: object,
) -> None:
    """Restore the original hot-water setpoint after treatment.

    On normal completion the setpoint is restored and the store is cleared.
    On graceful shutdown a best-effort restore is attempted with a short
    timeout so the boiler isn't left at the elevated temperature.  If the
    write fails the store remains active and crash recovery handles it on
    next startup.
    """
    if not ctx.shutdown_requested:
        await ctx.publish_state(
            {
                "status": "restoring",
                "original_setpoint": original_setpoint,
            }
        )
        await port.write_signal(LEGIONELLA_SETPOINT_SIGNAL, original_setpoint)
        store.update({_STORE_KEY_ACTIVE: False, _STORE_KEY_ORIGINAL_SETPOINT: None})
        store.save()
        await ctx.publish_state({"status": "idle"})
    else:
        # Graceful shutdown — best-effort restore so the boiler doesn't
        # remain at the elevated temperature between restarts.
        try:
            await asyncio.wait_for(
                port.write_signal(LEGIONELLA_SETPOINT_SIGNAL, original_setpoint),
                timeout=5,
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to restore setpoint during shutdown; "
                "recovery will handle it on next startup",
                exc_info=True,
            )
        else:
            store.update({_STORE_KEY_ACTIVE: False, _STORE_KEY_ORIGINAL_SETPOINT: None})
            store.save()


async def _handle_start(
    ctx: DeviceContext,
    store: DeviceStore,
    port: OptolinkPort,
    settings: Vito2MqttSettings,
    command_queue: asyncio.Queue[str],
) -> None:
    """Execute a full start → heat → restore cycle.

    Delegates the minute-by-minute countdown to :func:`_heating_countdown`
    and the setpoint restoration to :func:`_restore_setpoint`.
    """
    # -- Checking phase -----------------------------------------------------
    await ctx.publish_state({"status": "checking"})

    now = datetime.now()  # noqa: DTZ005
    weekday = now.weekday()
    timer_signal = TIMER_SIGNAL_FOR_DAY[weekday]
    schedule = await port.read_signal(timer_signal)

    feasible = is_within_heating_window(
        schedule,
        now.time(),
        safety_margin_minutes=settings.legionella_safety_margin_minutes,
    )
    if not feasible:
        reason = (
            f"Current time {now.time():%H:%M} is outside the "
            f"heating window for {timer_signal}"
        )
        logger.info("Legionella treatment rejected: %s", reason)
        await ctx.publish_state({"status": "rejected", "reason": reason})
        await ctx.publish_state({"status": "idle"})
        return

    # -- Save original setpoint ---------------------------------------------
    original_setpoint = await port.read_signal(LEGIONELLA_SETPOINT_SIGNAL)
    store.update(
        {
            _STORE_KEY_ORIGINAL_SETPOINT: original_setpoint,
            _STORE_KEY_ACTIVE: True,
        }
    )
    store.save()

    # -- Set treatment temperature ------------------------------------------
    target_temp = settings.legionella_temperature
    await port.write_signal(LEGIONELLA_SETPOINT_SIGNAL, target_temp)

    remaining_minutes: int = settings.legionella_duration_minutes
    logger.info(
        "Legionella treatment started — target=%s, duration=%d min",
        target_temp,
        remaining_minutes,
    )

    # -- Heating countdown --------------------------------------------------
    await ctx.publish_state(
        {
            "status": "heating",
            "target_temperature": target_temp,
            "original_setpoint": original_setpoint,
            "remaining_minutes": remaining_minutes,
        }
    )

    await _heating_countdown(
        ctx,
        command_queue,
        target_temp,
        original_setpoint,
        remaining_minutes,
    )

    # -- Restore original setpoint ------------------------------------------
    await _restore_setpoint(ctx, store, port, original_setpoint)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_legionella(app: App) -> None:
    """Register the legionella treatment device on *app*.

    This is the imperative entry point called from the application's
    startup wiring (main.py).  It delegates to
    :meth:`cosalette.App.add_device` with the correct device name and
    async handler function.

    Parameters:
        app: The cosalette application instance.
    """
    app.add_device("legionella", _legionella_device)
