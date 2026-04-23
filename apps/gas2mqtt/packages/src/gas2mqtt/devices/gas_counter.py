"""Gas counter telemetry — stateful trigger detection and counting.

Uses shared GasCounterState instance created in lifespan and injected via DI.
Telemetry handler is called periodically (poll_interval).
Command handler processes MQTT consumption updates.

Scheduled runs: read magnetometer, detect trigger edges, count ticks.
Command runs: set consumption value from MQTT command payload.

State persistence:
    GasCounterState wraps a DeviceStore. stage_state() explicitly
    calls store.save() to persist counter and consumption on changes.
    Counter and consumption survive restarts.

MQTT state payload:
    {"counter": 42, "trigger": "CLOSED"}
    or with consumption:
    {"counter": 42, "trigger": "CLOSED", "consumption_m3": 123.45}

MQTT command payload (on gas2mqtt/gas_counter/consumption/set):
    {"consumption_m3": 123.45}
"""

from __future__ import annotations

import math
import json
import logging

from cosalette import DeviceStore

from gas2mqtt.domain.consumption import ConsumptionTracker
from gas2mqtt.domain.schmitt import SchmittTrigger, TriggerState
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

COUNTER_MODULUS = 0x10000
MAX_CONSUMPTION_M3 = 1_000_000.0


class GasCounterState:
    """Mutable state container for the gas counter.

    Created once by make_gas_counter() init factory, persists across
    all scheduled and triggered telemetry runs.
    """

    def __init__(
        self,
        trigger: SchmittTrigger,
        counter: int,
        consumption: ConsumptionTracker | None,
        store: DeviceStore,
    ) -> None:
        self.trigger = trigger
        self.counter = counter
        self.consumption = consumption
        self.store = store

    def build_state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "counter": self.counter,
            "trigger": "CLOSED" if self.trigger.state is TriggerState.HIGH else "OPEN",
        }
        if self.consumption is not None:
            state["consumption_m3"] = round(self.consumption.consumption_m3, 3)
        return state

    def stage_state(self) -> None:
        state = self.build_state()
        state.pop("trigger", None)
        self.store.update(state)
        self.store.save()  # explicit save — not relying on SaveOnChange


def _restore_counter(store: DeviceStore, logger: logging.Logger) -> int:
    """Restore tick counter from saved state. Returns 0 if absent."""
    raw = store.get("counter", 0)
    counter = int(raw) if isinstance(raw, (int, float, str)) else 0
    if counter != 0:
        logger.info("Restored counter=%d from saved state", counter)
    return counter


def _restore_consumption(
    store: DeviceStore,
    settings: Gas2MqttSettings,
    logger: logging.Logger,
) -> ConsumptionTracker | None:
    """Restore consumption tracker from saved state. None if disabled."""
    if not settings.enable_consumption_tracking:
        return None
    initial_m3 = 0.0
    raw = store.get("consumption_m3")
    if raw is not None:
        initial_m3 = float(raw) if isinstance(raw, (int, float, str)) else 0.0
        logger.info("Restored consumption=%.3f m³ from saved state", initial_m3)
    return ConsumptionTracker(settings.liters_per_tick, initial_m3=initial_m3)


def _parse_consumption_m3(
    raw_value: object,
    logger: logging.Logger,
) -> float | None:
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float, str)):
        logger.warning("Ignoring invalid consumption_m3 payload: %r", raw_value)
        return None

    try:
        value = float(raw_value)
    except TypeError, ValueError:
        logger.warning("Ignoring invalid consumption_m3 payload: %r", raw_value)
        return None

    if not math.isfinite(value):
        logger.warning("Ignoring non-finite consumption_m3 payload: %r", raw_value)
        return None
    if value < 0:
        logger.warning("Ignoring negative consumption_m3 payload: %r", raw_value)
        return None
    if value > MAX_CONSUMPTION_M3:
        logger.warning(
            "Ignoring out-of-range consumption_m3 payload: %r",
            raw_value,
        )
        return None
    return value


def make_gas_counter(
    settings: Gas2MqttSettings,
    store: DeviceStore,
    logger: logging.Logger,
) -> GasCounterState:
    """Init factory — creates stateful domain objects.

    Called once before the telemetry loop. The returned GasCounterState
    is injected into gas_counter() on every scheduled and triggered run.
    """
    store.load()
    trigger = SchmittTrigger(settings.trigger_level, settings.trigger_hysteresis)
    counter = _restore_counter(store, logger)
    consumption = _restore_consumption(store, settings, logger)
    return GasCounterState(trigger, counter, consumption, store)


async def gas_counter(
    state: GasCounterState,
    magnetometer: MagnetometerPort,
    logger: logging.Logger,
) -> dict[str, object] | None:
    """Gas counter telemetry handler (read-only).

    Called periodically to read magnetometer and count ticks.
    Returns dict to publish, or None to skip.
    """
    return _poll(state, magnetometer, logger)


async def update_consumption(
    payload: str,
    state: GasCounterState,
    logger: logging.Logger,
) -> dict[str, object] | None:
    """Handle inbound MQTT command to set consumption value.

    Expects JSON payload: {"consumption_m3": <float>}
    Publishes updated state on success; returns None if disabled or invalid.
    """
    if state.consumption is None:
        logger.warning("Consumption command received but tracking is disabled")
        return None

    if not payload.strip():
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Ignoring invalid JSON in consumption command")
        return None

    if not isinstance(data, dict):
        logger.warning("Ignoring non-object JSON in consumption command")
        return None

    if "consumption_m3" in data:
        consumption_m3 = _parse_consumption_m3(data["consumption_m3"], logger)
        if consumption_m3 is None:
            return None
        state.consumption.set_consumption(consumption_m3)
        logger.info("Consumption set to %.3f m³", state.consumption.consumption_m3)
        state.stage_state()
        return state.build_state()
    return None


def _poll(
    state: GasCounterState,
    magnetometer: MagnetometerPort,
    logger: logging.Logger,
) -> dict[str, object] | None:
    """Read magnetometer, process trigger, return state if changed."""
    reading = magnetometer.read()
    event = state.trigger.update(reading.bz)
    if event is None:
        return None  # No state change — framework skips publish
    if event.is_rising_edge:
        state.counter = (state.counter + 1) % COUNTER_MODULUS
        if state.consumption is not None:
            state.consumption.tick()
        logger.debug("Gas tick: counter=%d", state.counter)
    state.stage_state()
    return state.build_state()
