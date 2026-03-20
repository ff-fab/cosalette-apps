"""JeeLink receiver device — serial read loop and frame dispatch.

Registers as a cosalette **root device** (``@app.device()`` with no
name), so topics publish directly under the application prefix::

    jeelink2mqtt/{sensor_name}/state      ← calibrated readings
    jeelink2mqtt/{sensor_name}/availability
    jeelink2mqtt/raw/state                ← every decoded frame
    jeelink2mqtt/mapping/state            ← current ID→name map
    jeelink2mqtt/mapping/event            ← mapping change events

The receiver manages the JeeLink adapter lifecycle and routes incoming
frames through the **filter → calibrate → publish** pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from datetime import UTC, datetime

import cosalette
from cosalette import DeviceStore

from jeelink2mqtt.app import SharedState, get_state
from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorReading
from jeelink2mqtt.ports import JeeLinkPort
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_receiver(app: cosalette.App) -> None:
    """Register the receiver as the root device on *app*."""

    @app.device()  # Root → topics at jeelink2mqtt/{channel}
    async def receiver(  # pragma: no cover — composition root, tested via integration
        ctx: cosalette.DeviceContext,
        jeelink: JeeLinkPort,
        store: DeviceStore,
        settings: Jeelink2MqttSettings,
    ) -> None:
        """Main receiver loop: open adapter, read frames, process, publish."""
        state = get_state()

        # -- Restore persisted registry state (if any) ---------------------
        _restore_registry(store, state, settings)

        # -- Bridge sync callbacks → async queue ---------------------------
        #
        # pylacrosse calls back from a serial reader *thread*, while
        # asyncio.Queue is not thread-safe.  We use call_soon_threadsafe
        # to safely enqueue from the foreign thread.
        queue: asyncio.Queue[SensorReading] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _on_reading(reading: SensorReading) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, reading)

        jeelink.open()
        jeelink.register_callback(_on_reading)
        jeelink.start_scan()
        logger.info("Receiver started — listening on %s", settings.serial_port)

        # Track last calibrated readings for heartbeat re-publish
        last_readings: dict[str, SensorReading] = {}
        last_publish_time: dict[str, datetime] = {}
        last_persist_time = datetime.now(UTC)

        try:
            while not ctx.shutdown_requested:
                try:
                    reading = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    await _check_staleness(ctx, settings, state)
                    await _maybe_heartbeat(
                        ctx,
                        settings,
                        state,
                        last_readings,
                        last_publish_time,
                    )
                    continue

                # 1. Raw diagnostic (every frame, non-retained)
                await _publish_raw(ctx, reading)

                # 2. Route through registry
                name = state.registry.record_reading(reading)

                # 3. Mapped → filter → calibrate → publish
                if name is not None:
                    config = state.sensor_configs.get(name)
                    if config is not None:
                        calibrated = _apply_pipeline(reading, config, state)
                        await _publish_sensor(ctx, name, calibrated)
                        last_readings[name] = calibrated
                        last_publish_time[name] = datetime.now(UTC)

                        await ctx.publish(
                            f"{name}/availability",
                            "online",
                            retain=True,
                        )

                # 4. Mapping events (only publish state when something changed)
                events = state.registry.drain_events()
                for event in events:
                    await _publish_mapping_event(ctx, event)
                    # Clean up stale filters for replaced sensor IDs
                    if event.old_sensor_id is not None:
                        state.filter_bank.reset(event.old_sensor_id)

                if events:
                    await _publish_mapping_state(ctx, state)
                    # Persist immediately on mapping changes
                    store["registry"] = state.registry.to_dict()
                    last_persist_time = datetime.now(UTC)

                # 5. Periodic persistence for last_seen metadata (ADR-004)
                # Avoids writing on every frame while still surviving restarts.
                now = datetime.now(UTC)
                if (now - last_persist_time).total_seconds() >= 60:
                    store["registry"] = state.registry.to_dict()
                    last_persist_time = now

        finally:
            # Publish all configured sensors as offline
            for sensor_cfg in settings.sensors:
                await ctx.publish(
                    f"{sensor_cfg.name}/availability",
                    "offline",
                    retain=True,
                )
            jeelink.stop_scan()
            jeelink.close()
            logger.info("Receiver stopped")


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _apply_pipeline(
    reading: SensorReading,
    config: SensorConfig,
    state: SharedState,
) -> SensorReading:
    """Filter → calibrate a raw reading, returning a new SensorReading."""
    temp, humidity = state.filter_bank.filter(reading)
    filtered = replace(reading, temperature=temp, humidity=int(humidity))
    return apply_calibration(filtered, config)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _restore_registry(
    store: DeviceStore,
    state: SharedState,
    settings: Jeelink2MqttSettings,
) -> None:
    """Restore persisted registry state from the device store.

    If the store contains a ``"registry"`` key from a previous run,
    we rebuild the :class:`SensorRegistry` from that snapshot so
    ID→name mappings survive restarts.
    """
    registry_data = store.get("registry")
    if registry_data is None:
        logger.info("No persisted registry state — starting fresh")
        return

    if not isinstance(registry_data, dict):
        logger.warning("Invalid persisted registry data — starting fresh")
        return

    configs = list(state.sensor_configs.values())
    state.registry = SensorRegistry.from_dict(
        registry_data,
        sensors=configs,
        staleness_timeout=settings.staleness_timeout_seconds,
    )
    logger.info(
        "Restored registry with %d mapping(s)",
        len(state.registry.get_all_mappings()),
    )


# ---------------------------------------------------------------------------
# Publishing helpers
# ---------------------------------------------------------------------------


async def _publish_raw(
    ctx: cosalette.DeviceContext,
    reading: SensorReading,
) -> None:
    """Publish raw diagnostic frame (non-retained)."""
    payload = json.dumps(
        {
            "sensor_id": reading.sensor_id,
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "low_battery": reading.low_battery,
            "timestamp": reading.timestamp.isoformat(),
        }
    )
    await ctx.publish("raw/state", payload, retain=False)


async def _publish_sensor(
    ctx: cosalette.DeviceContext,
    name: str,
    reading: SensorReading,
) -> None:
    """Publish calibrated sensor state (retained)."""
    payload = json.dumps(
        {
            "temperature": round(reading.temperature, 2),
            "humidity": reading.humidity,
            "low_battery": reading.low_battery,
            "timestamp": reading.timestamp.isoformat(),
        }
    )
    await ctx.publish(f"{name}/state", payload, retain=True)


async def _publish_mapping_event(
    ctx: cosalette.DeviceContext,
    event: MappingEvent,
) -> None:
    """Publish a mapping change event (non-retained)."""
    payload = json.dumps(
        {
            "event_type": event.event_type,
            "sensor_name": event.sensor_name,
            "old_sensor_id": event.old_sensor_id,
            "new_sensor_id": event.new_sensor_id,
            "timestamp": event.timestamp.isoformat(),
            "reason": event.reason,
        }
    )
    await ctx.publish("mapping/event", payload, retain=False)


async def _publish_mapping_state(
    ctx: cosalette.DeviceContext,
    state: SharedState,
) -> None:
    """Publish current mapping state snapshot (retained)."""
    mapping_state = {
        name: {
            "sensor_id": m.sensor_id,
            "mapped_at": m.mapped_at.isoformat(),
            "last_seen": m.last_seen.isoformat(),
        }
        for name, m in state.registry.get_all_mappings().items()
    }
    await ctx.publish("mapping/state", json.dumps(mapping_state), retain=True)


# ---------------------------------------------------------------------------
# Staleness & heartbeat
# ---------------------------------------------------------------------------


async def _check_staleness(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """Publish ``offline`` availability for any stale sensors."""
    for sensor_cfg in settings.sensors:
        if state.registry.is_stale(sensor_cfg.name):
            await ctx.publish(
                f"{sensor_cfg.name}/availability",
                "offline",
                retain=True,
            )


async def _maybe_heartbeat(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
    last_readings: dict[str, SensorReading],
    last_publish_time: dict[str, datetime],
) -> None:
    """Re-publish sensor state if the heartbeat interval has elapsed.

    This ensures Home Assistant (or other consumers) receive periodic
    updates even when a sensor's readings haven't changed, preventing
    entity unavailability due to MQTT inactivity.
    """
    now = datetime.now(UTC)
    interval = settings.heartbeat_interval_seconds

    for sensor_cfg in settings.sensors:
        name = sensor_cfg.name
        if state.registry.is_stale(name):
            continue

        last_time = last_publish_time.get(name)
        if last_time is None or (now - last_time).total_seconds() < interval:
            continue

        # Re-publish last known calibrated reading if available
        last = last_readings.get(name)
        if last is not None:
            await _publish_sensor(ctx, name, last)

        await ctx.publish(f"{name}/availability", "online", retain=True)
        last_publish_time[name] = now
