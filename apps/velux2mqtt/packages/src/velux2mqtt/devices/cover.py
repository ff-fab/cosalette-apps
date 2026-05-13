"""Cover device — GPIO-driven position control for Velux covers.

A "cover" is Home Assistant's term for blinds, shutters, windows, and
similar openable devices.  Each cover (e.g. blind, window) is registered
as a cosalette device via :func:`make_cover`.
The device function owns the MQTT command loop: it parses inbound
payloads, plans moves through the DriftCompensator, executes GPIO
button presses, and publishes position state.

Startup homing (optional) moves the cover to a known endpoint on
boot so the position tracker starts from a reliable reference.

Calibration commands arrive on the ``calibrate`` sub-topic
(``velux2mqtt/{device}/calibrate/set``) with payload ``{"phase": "start|go|mark|cancel"}``.
A background task manages calibration lifecycle inside ``ctx.sub_entity("calibrate")``
so that ``calibrate/availability`` goes online/offline automatically.
During active calibration normal cover commands are blocked.

Command flow:
    MQTT payload -> parse_command() -> DriftCompensator.plan_move()
    -> for each MoveStep: press GPIO pin -> sleep(travel_time)
    -> press stop (intermediate moves only) -> update PositionTracker
    -> publish state

Endpoint moves (0% or 100%) let the motor stall at the physical limit
and skip the explicit STOP press.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Literal

import cosalette

from velux2mqtt.domain.calibration import (
    CalibrationDirection,
    CalibrationError,
    CalibrationState,
    CalibrationStateMachine,
)
from velux2mqtt.domain.command import (
    Direction,
    InvalidCommandError,
    parse_command,
)
from velux2mqtt.domain.drift import DriftCompensator, MoveStep
from velux2mqtt.domain.position import PositionTracker
from velux2mqtt.ports import GpioSwitchPort
from velux2mqtt.settings import CoverConfig, Velux2MqttSettings


def make_cover(
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
) -> Callable[..., Awaitable[None]]:
    """Create a cover device function for registration with cosalette.

    Returns an async callable with the signature expected by
    ``app.add_device(name, func)``.  The returned function captures
    *cover_cfg* and *settings* via closure.

    Args:
        cover_cfg: Per-cover configuration (pins, travel durations).
        settings: Application-wide settings (button press duration, homing, drift).

    Returns:
        Async device function suitable for ``app.add_device``.
    """

    async def cover_device(ctx: cosalette.DeviceContext) -> AsyncIterator[None]:
        gpio: GpioSwitchPort = ctx.adapter(GpioSwitchPort)  # type: ignore[type-abstract]
        logger = logging.getLogger(f"cosalette.{ctx.name}")

        tracker = PositionTracker(
            travel_duration_up=cover_cfg.travel_duration_up,
            travel_duration_down=cover_cfg.travel_duration_down,
            travel_time_offset=cover_cfg.travel_time_offset,
        )
        drift = DriftCompensator(threshold=settings.drift_recalibration_threshold)
        calibration = CalibrationStateMachine()

        # Internal queue: calibrate sub-topic commands → calibration background task
        _cal_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        @ctx.on_command("calibrate")
        async def _route_calibrate(_sub_topic: str | None, payload: str) -> None:
            params = _parse_calibrate(
                payload
            )  # Now looks for {"phase": "start/go/mark/cancel"}
            if params is not None:
                await _cal_queue.put(params)
            else:
                logger.warning("Invalid calibration payload: %s", payload)

        # Background task manages calibration sub_entity lifecycle
        cal_task = asyncio.create_task(
            _run_calibration_task(
                ctx=ctx,
                gpio=gpio,
                cover_cfg=cover_cfg,
                settings=settings,
                calibration=calibration,
                cal_queue=_cal_queue,
                logger=logger,
            )
        )

        try:
            # --- Startup homing ---
            if settings.enable_startup_homing:
                await _run_homing(
                    ctx=ctx,
                    gpio=gpio,
                    cover_cfg=cover_cfg,
                    settings=settings,
                    tracker=tracker,
                    logger=logger,
                )

            # Publish initial state
            await _publish_position(ctx, tracker)

            # --- Command loop ---
            async for cmd in ctx.commands():
                if cmd is None:  # Type guard for safety
                    continue
                payload = cmd.payload

                # Block normal commands during active calibration (no intercept anymore)
                if calibration.state in (
                    CalibrationState.READY,
                    CalibrationState.TIMING_OFFSET,
                    CalibrationState.TIMING_DEAD_BAND,
                    CalibrationState.TIMING,
                ):
                    logger.warning(
                        "Calibration active (%s), ignoring command: %s",
                        calibration.state.name,
                        payload,
                    )
                    continue

                try:
                    command = parse_command(payload)
                except InvalidCommandError as exc:
                    logger.warning("Invalid command: %s", exc)
                    continue

                if command.direction is Direction.STOP:
                    await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
                    tracker.stop()
                    drift.reset()
                    await _publish_position(ctx, tracker)
                    yield
                    continue

                target = command.position
                if target is None:
                    logger.warning("Command has no target position, ignoring")
                    continue

                steps = drift.plan_move(tracker.position, target)
                for step in steps:
                    if ctx.shutdown_requested:
                        break
                    await _execute_step(
                        ctx=ctx,
                        gpio=gpio,
                        cover_cfg=cover_cfg,
                        settings=settings,
                        tracker=tracker,
                        step=step,
                        logger=logger,
                    )
                    await _publish_position(ctx, tracker)
                yield

        finally:
            cal_task.cancel()
            try:
                await cal_task
            except asyncio.CancelledError:
                pass

    return cover_device


async def _run_homing(
    *,
    ctx: cosalette.DeviceContext,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
    tracker: PositionTracker,
    logger: logging.Logger,
) -> None:
    """Move cover to a known endpoint on startup.

    Presses the homing direction button, waits for full travel plus
    a safety margin, then presses stop to ensure the motor halts.
    Finalizes the tracker at the endpoint.

    Args:
        ctx: Device context for shutdown-aware sleep.
        gpio: GPIO adapter for button presses.
        cover_cfg: Cover pin and travel configuration.
        settings: Application settings (homing direction, button press duration).
        tracker: Position tracker to finalize at endpoint.
        logger: Logger for status messages.
    """
    if settings.homing_direction == "close":
        pin = cover_cfg.pin_down
        travel = cover_cfg.travel_duration_down
    else:
        pin = cover_cfg.pin_up
        travel = cover_cfg.travel_duration_up

    logger.info(
        "Homing %s: %s for %.1fs",
        cover_cfg.name,
        settings.homing_direction,
        travel + cover_cfg.max_timer_margin,
    )

    # Press direction button
    await gpio.press(pin, settings.button_press_duration)

    # Wait for full travel + margin
    await ctx.sleep(travel + cover_cfg.max_timer_margin)

    if ctx.shutdown_requested:
        # Best-effort stop to avoid leaving the motor running
        await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
        return

    # Press stop
    await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)

    # Finalize position
    if settings.homing_direction == "close":
        tracker.finalize_closed()
    else:
        tracker.finalize_open()

    logger.info("Homing complete: position=%d%%", tracker.position_int)


def _dead_band_time(cover_cfg: CoverConfig, direction: Literal["up", "down"]) -> float:
    """Calculate dead band traversal time in seconds.

    The dead band is the portion of total travel where the handle
    rotates but the cover does not yet move.  ``dead_band_pct`` is
    defined as a percentage of *total* travel (dead band + effective
    movement), so the inversion is ``db = f/(1-f) * effective``.

    Args:
        cover_cfg: Cover configuration with dead_band_pct.
        direction: ``"up"`` or ``"down"``.

    Returns:
        Seconds for dead band traversal, or 0.0 if disabled.
    """
    if cover_cfg.dead_band_pct <= 0:
        return 0.0
    fraction = cover_cfg.dead_band_pct / 100.0
    scale = fraction / (1.0 - fraction)
    if direction == "up":
        return scale * cover_cfg.travel_duration_up
    return scale * cover_cfg.travel_duration_down


async def _execute_step(
    *,
    ctx: cosalette.DeviceContext,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
    tracker: PositionTracker,
    step: MoveStep,
    logger: logging.Logger,
) -> None:
    """Execute a single movement step (direct or recalibration).

    For endpoint targets (0 or 100), uses full travel + margin and
    finalizes the tracker at the endpoint.  For intermediate targets,
    calculates travel time from the current position and stops after
    the computed duration.

    When dead band is configured:

    - **Opening from 0%**: the button is pressed once and the system
      waits for the dead band time (handle rotation) before starting
      the position tracker.  The handle and cover move in one
      continuous motion.
    - **Closing to 0%**: after the effective cover travel completes,
      the system waits an additional dead band time for the handle to
      close before pressing stop.
    - The dead band is never stopped within -- the handle always fully
      opens or fully closes.

    Args:
        ctx: Device context for shutdown-aware sleep.
        gpio: GPIO adapter for button presses.
        cover_cfg: Cover pin and travel configuration.
        settings: Application settings (button press duration).
        tracker: Position tracker to update.
        step: The MoveStep to execute.
        logger: Logger for status messages.
    """
    current = tracker.position
    target = step.target

    if target == tracker.position_int and not step.is_recalibration:
        return  # Already at target

    opening = target > current
    needs_open_dead_band = (
        opening and tracker.position_int == 0 and _dead_band_time(cover_cfg, "up") > 0
    )

    # Determine direction
    if opening:
        pin = cover_cfg.pin_up
    else:
        pin = cover_cfg.pin_down

    # Calculate travel time
    if target in (0, 100):
        # Full travel to endpoint: use full duration + margin
        if target == 100:
            travel_time = cover_cfg.travel_duration_up + cover_cfg.max_timer_margin
        else:
            travel_time = cover_cfg.travel_duration_down + cover_cfg.max_timer_margin
    else:
        travel_time = tracker.travel_time_for(current, target)

    # Dead band: when opening from 0, press button and wait for handle
    # rotation before starting the position tracker
    if needs_open_dead_band:
        db_time = _dead_band_time(cover_cfg, "up")
        logger.info(
            "Dead band %s: opening handle (%.1fs) then moving to %d%%",
            cover_cfg.name,
            db_time,
            target,
        )
        await gpio.press(pin, settings.button_press_duration)
        await ctx.sleep(db_time)
        if ctx.shutdown_requested:
            await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
            return
        # Now start tracking effective movement (handle is open)
        tracker.start_opening()
    else:
        logger.info(
            "Moving %s: %d%% -> %d%% (%.1fs)%s",
            cover_cfg.name,
            round(current),
            target,
            travel_time,
            " [recalibration]" if step.is_recalibration else "",
        )
        if opening:
            tracker.start_opening()
        else:
            tracker.start_closing()
        await gpio.press(pin, settings.button_press_duration)

    # Wait for travel
    await ctx.sleep(travel_time)

    if ctx.shutdown_requested:
        await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
        tracker.stop()
        return

    # Dead band: when closing to 0, wait for handle to close after
    # effective travel completes (motor is still running)
    db_close = _dead_band_time(cover_cfg, "down")
    if target == 0 and db_close > 0:
        logger.info(
            "Dead band %s: closing handle (%.1fs)",
            cover_cfg.name,
            db_close,
        )
        await ctx.sleep(db_close)
        if ctx.shutdown_requested:
            await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
            tracker.stop()
            return

    # Finalize position — endpoint moves let the motor stall at the
    # physical limit so no STOP press is needed.  Intermediate moves
    # must be stopped explicitly.
    if target == 0:
        tracker.finalize_closed()
    elif target == 100:
        tracker.finalize_open()
    else:
        await gpio.press(cover_cfg.pin_stop, settings.button_press_duration)
        tracker.stop()


async def _publish_position(
    ctx: cosalette.DeviceContext,
    tracker: PositionTracker,
) -> None:
    """Publish current position state to MQTT.

    Payload format: ``{"position": <int 0-100>}``
    """
    await ctx.publish_state({"position": tracker.position_int})


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------

_CALIBRATE_ACTIONS = frozenset({"start", "go", "mark", "cancel"})


def _parse_calibrate(payload: str) -> dict[str, object] | None:
    """Extract calibration parameters from a JSON payload from the calibrate sub-topic.

    Expects format: {"phase": "start|go|mark|cancel", ...extra}
    Returns a dict with at least ``{"action": "<action>"}`` on success,
    plus any extra fields (e.g. ``runs``).
    """
    text = payload.strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    action = data.get("phase")
    if isinstance(action, str) and action in _CALIBRATE_ACTIONS:
        result: dict[str, object] = {"action": action}
        if "runs" in data:
            result["runs"] = data["runs"]
        if "measure_offset" in data and isinstance(data["measure_offset"], bool):
            result["measure_offset"] = data["measure_offset"]
        if "measure_dead_band" in data and isinstance(data["measure_dead_band"], bool):
            result["measure_dead_band"] = data["measure_dead_band"]
        if "starting_state" in data and isinstance(data["starting_state"], str):
            result["starting_state"] = data["starting_state"]
        return result
    return None


async def _run_calibration_task(
    *,
    ctx: cosalette.DeviceContext,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
    calibration: CalibrationStateMachine,
    cal_queue: asyncio.Queue[dict[str, object]],
    logger: logging.Logger,
) -> None:
    """Background task: manages calibration sub_entity lifecycle."""
    while not ctx.shutdown_requested:
        # Wait for a "start" command
        try:
            params = await asyncio.wait_for(cal_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        if params.get("action") != "start":
            logger.warning(
                "Expected 'start' calibration action, got: %r", params.get("action")
            )
            continue

        # === Calibration active: manage sub_entity lifecycle ===
        async with ctx.sub_entity("calibrate") as cal:
            try:
                runs_raw = params.get("runs", settings.calibration_runs)
                runs = (
                    int(runs_raw)
                    if isinstance(runs_raw, (int, str))
                    else settings.calibration_runs
                )
                measure_off_raw = params.get("measure_offset", cover_cfg.measure_offset)
                measure_off = (
                    bool(measure_off_raw)
                    if isinstance(measure_off_raw, bool)
                    else cover_cfg.measure_offset
                )
                measure_db_raw = params.get("measure_dead_band", False)
                measure_db = (
                    bool(measure_db_raw) if isinstance(measure_db_raw, bool) else False
                )
                starting_st_raw = params.get("starting_state", "closed")
                starting_st = (
                    str(starting_st_raw)
                    if isinstance(starting_st_raw, str)
                    else "closed"
                )
                calibration.start(
                    runs=runs,
                    measure_offset=measure_off,
                    measure_dead_band=measure_db,
                    starting_state=starting_st,
                )
            except (ValueError, CalibrationError) as exc:
                logger.warning("Calibration start error: %s", exc)
                await _publish_calibration_state(cal, calibration)
                continue

            await _publish_calibration_state(cal, calibration)

            await _run_active_calibration_session(
                ctx=ctx,
                gpio=gpio,
                cover_cfg=cover_cfg,
                settings=settings,
                calibration=calibration,
                cal=cal,
                cal_queue=cal_queue,
                logger=logger,
            )
            _drain_calibration_queue(cal_queue)
        # sub_entity exits → calibrate/availability = "offline"


def _calibration_progress(
    calibration: CalibrationStateMachine,
) -> tuple[CalibrationState, int, CalibrationDirection]:
    """Return a marker that changes only when calibration meaningfully advances."""
    return (calibration.state, calibration.current_run, calibration.direction)


async def _dispatch_calibration_event(
    *,
    event,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
) -> None:
    """Apply the GPIO side effect requested by a calibration transition."""
    if not event.press_button or event.direction is None:
        return

    pin = (
        cover_cfg.pin_down
        if event.direction is CalibrationDirection.CLOSE
        else cover_cfg.pin_up
    )
    await gpio.press(pin, settings.button_press_duration)


async def _process_calibration_action(
    *,
    action: object,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
    calibration: CalibrationStateMachine,
    logger: logging.Logger,
) -> bool:
    """Apply one calibration action and report whether it advanced the session."""
    before = _calibration_progress(calibration)

    try:
        if action == "go":
            event = calibration.go()
            await _dispatch_calibration_event(
                event=event,
                gpio=gpio,
                cover_cfg=cover_cfg,
                settings=settings,
            )
        elif action == "mark":
            event = calibration.mark()
            await _dispatch_calibration_event(
                event=event,
                gpio=gpio,
                cover_cfg=cover_cfg,
                settings=settings,
            )
        elif action == "cancel":
            calibration.cancel()
        else:
            logger.warning("Unknown calibration action: %r", action)
            return False
    except (CalibrationError, ValueError, TypeError) as exc:
        logger.warning("Calibration error: %s", exc)
        return False

    return _calibration_progress(calibration) != before


async def _publish_calibration_result(
    *,
    ctx: cosalette.DeviceContext,
    calibration: CalibrationStateMachine,
    logger: logging.Logger,
) -> None:
    """Publish the final calibration result payload."""
    result_data: dict[str, object] = {
        "avg_close": round(calibration.average_close, 2),
        "avg_open": round(calibration.average_open, 2),
    }
    db_pct = 0.0
    if calibration.has_offset:
        result_data["avg_offset"] = round(calibration.average_offset, 2)
    if calibration.has_dead_band:
        db_pct = calibration.dead_band_pct(
            calibration.average_close,
            calibration.average_open,
        )
        result_data["avg_dead_band"] = round(calibration.average_dead_band, 2)
        result_data["dead_band_pct"] = round(db_pct, 1)

    parts = [
        f"avg_close={calibration.average_close:.2f}s",
        f"avg_open={calibration.average_open:.2f}s",
    ]
    if calibration.has_offset:
        parts.append(f"avg_offset={calibration.average_offset:.2f}s")
    if calibration.has_dead_band:
        parts.append(
            f"avg_dead_band={calibration.average_dead_band:.2f}s ({db_pct:.1f}%)"
        )

    logger.info("Calibration complete: %s", ", ".join(parts))
    await ctx.publish("calibrate/result", json.dumps(result_data), retain=True)


def _drain_calibration_queue(cal_queue: asyncio.Queue[dict[str, object]]) -> None:
    """Discard stale calibration actions left over from the previous session."""
    while True:
        try:
            cal_queue.get_nowait()
        except asyncio.QueueEmpty:
            return


async def _run_active_calibration_session(
    *,
    ctx: cosalette.DeviceContext,
    gpio: GpioSwitchPort,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
    calibration: CalibrationStateMachine,
    cal: cosalette.SubEntityContext,
    cal_queue: asyncio.Queue[dict[str, object]],
    logger: logging.Logger,
) -> None:
    """Run one active calibration session with a fixed inactivity deadline."""
    deadline = ctx.clock.now() + 120.0

    while calibration.state is not CalibrationState.IDLE:
        remaining = deadline - ctx.clock.now()
        if remaining <= 0:
            logger.warning("Calibration timed out, cancelling")
            calibration.cancel()
            await _publish_calibration_state(cal, calibration)
            return

        try:
            params = await asyncio.wait_for(cal_queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            logger.warning("Calibration timed out, cancelling")
            calibration.cancel()
            await _publish_calibration_state(cal, calibration)
            return

        advanced = await _process_calibration_action(
            action=params.get("action"),
            gpio=gpio,
            cover_cfg=cover_cfg,
            settings=settings,
            calibration=calibration,
            logger=logger,
        )

        await _publish_calibration_state(cal, calibration)

        if calibration.state is CalibrationState.COMPLETE:
            await _publish_calibration_result(
                ctx=ctx,
                calibration=calibration,
                logger=logger,
            )
            return

        if advanced:
            deadline = ctx.clock.now() + 120.0


async def _publish_calibration_state(
    cal: cosalette.SubEntityContext,
    calibration: CalibrationStateMachine,
) -> None:
    """Publish current calibration state to MQTT via sub-entity context."""
    payload: dict[str, object] = {"state": calibration.state.name}
    if calibration.state is not CalibrationState.IDLE:
        payload["run"] = calibration.current_run
        payload["total_runs"] = calibration.total_runs
        payload["direction"] = calibration.direction.name
    await cal.publish_state(payload)
