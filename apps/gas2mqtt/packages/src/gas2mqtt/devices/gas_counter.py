"""Gas counter device — stateful trigger detection and counting.

Uses an @app.device handler with a manual polling loop:
1. Reads Bz from the magnetometer at poll_interval
2. Feeds Bz into a SchmittTrigger
3. On rising edge: increments counter, optionally tracks consumption
4. Publishes state on every trigger event (not every poll)
5. Accepts inbound commands to set consumption value

State persistence:
    When ``state_file`` is configured, counter and consumption values
    are saved after every state-publishing event and on shutdown.
    On startup, saved state is restored so values survive restarts.
    The trigger state is transient and not persisted.

MQTT state payload:
    {"counter": 42, "trigger": "CLOSED"}
    or with consumption tracking:
    {"counter": 42, "trigger": "CLOSED", "consumption_m3": 123.45}

MQTT command payload (on gas2mqtt/gas_counter/set):
    {"consumption_m3": 123.45}
"""

from __future__ import annotations

import json
import logging

import cosalette

from gas2mqtt.domain.consumption import ConsumptionTracker
from gas2mqtt.domain.schmitt import SchmittTrigger, TriggerState
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

COUNTER_MODULUS = 0x10000
"""Modulus for the tick counter (wraps at 2^16)."""


def _process_poll(
    magnetometer: MagnetometerPort,
    trigger: SchmittTrigger,
    counter: int,
    consumption: ConsumptionTracker | None,
    logger: logging.Logger,
) -> tuple[int, bool]:
    """Read magnetometer and process trigger event.

    Returns:
        Tuple of (updated counter, whether state should be published).

    Raises:
        OSError: If the I2C read fails.
    """
    reading = magnetometer.read()
    event = trigger.update(reading.bz)
    if event is None:
        return counter, False
    if event.is_rising_edge:
        counter = (counter + 1) % COUNTER_MODULUS
        if consumption is not None:
            consumption.tick()
        logger.debug("Gas tick: counter=%d", counter)
    return counter, True


def _restore_counter(
    store: cosalette.DeviceStore,
    logger: logging.Logger,
) -> int:
    """Restore the tick counter from saved state.

    Returns 0 if the store has no counter value.
    """
    raw = store.get("counter", 0)
    counter = int(raw) if isinstance(raw, (int, float, str)) else 0
    if counter != 0:
        logger.info("Restored counter=%d from saved state", counter)
    return counter


def _restore_consumption(
    store: cosalette.DeviceStore,
    settings: Gas2MqttSettings,
    logger: logging.Logger,
) -> ConsumptionTracker | None:
    """Restore consumption tracker from saved state.

    Returns None if consumption tracking is disabled.
    """
    if not settings.enable_consumption_tracking:
        return None
    initial_m3 = 0.0
    raw = store.get("consumption_m3")
    if raw is not None:
        initial_m3 = float(raw) if isinstance(raw, (int, float, str)) else 0.0
        logger.info(
            "Restored consumption=%.3f m³ from saved state",
            initial_m3,
        )
    return ConsumptionTracker(settings.liters_per_tick, initial_m3=initial_m3)


async def gas_counter(
    ctx: cosalette.DeviceContext,
    store: cosalette.DeviceStore,
) -> None:
    """Gas counter device — polls magnetometer, detects ticks.

    This is a long-running device coroutine intended for registration
    with ``@app.device("gas_counter")``. It owns its polling loop,
    manages a SchmittTrigger for edge detection, and optionally tracks
    cumulative gas consumption.

    Args:
        ctx: Per-device context injected by cosalette. Provides MQTT
            publishing, shutdown-aware sleep, adapter resolution,
            and settings access.
        store: Per-device persistent store injected by cosalette.
            Already loaded on entry; saved by framework on shutdown.
    """
    settings: Gas2MqttSettings = ctx.settings  # type: ignore[assignment]
    magnetometer = ctx.adapter(MagnetometerPort)  # type: ignore[type-abstract]
    logger = logging.getLogger(f"cosalette.{ctx.name}")

    # --- Domain object initialisation ---
    trigger = SchmittTrigger(settings.trigger_level, settings.trigger_hysteresis)

    # --- Restore persisted state ---
    counter = _restore_counter(store, logger)
    consumption = _restore_consumption(store, settings, logger)

    def _build_state() -> dict[str, object]:
        """Build the state payload dict."""
        state: dict[str, object] = {
            "counter": counter,
            "trigger": "CLOSED" if trigger.state is TriggerState.HIGH else "OPEN",
        }
        if consumption is not None:
            state["consumption_m3"] = round(consumption.consumption_m3, 3)
        return state

    @ctx.on_command
    async def handle_command(topic: str, payload: str) -> None:  # noqa: ARG001
        nonlocal consumption
        if consumption is None:
            logger.warning("Consumption command received but tracking is disabled")
            return
        try:
            data = json.loads(payload)
            if "consumption_m3" in data:
                consumption.set_consumption(float(data["consumption_m3"]))
                logger.info("Consumption set to %.3f m³", consumption.consumption_m3)
                await ctx.publish_state(_build_state())
                _save_state()
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("Invalid consumption command: %s", exc)

    def _save_state() -> None:
        """Persist current state to the device store."""
        state = _build_state()
        # Remove trigger — it's transient, not worth persisting
        state.pop("trigger", None)
        store.update(state)
        store.save()

    # Publish initial state
    await ctx.publish_state(_build_state())
    _save_state()

    while not ctx.shutdown_requested:
        try:
            counter, should_publish = _process_poll(
                magnetometer,
                trigger,
                counter,
                consumption,
                logger,
            )
            if should_publish:
                await ctx.publish_state(_build_state())
                _save_state()
        except OSError:
            logger.exception("I2C read error")
        await ctx.sleep(settings.poll_interval)
