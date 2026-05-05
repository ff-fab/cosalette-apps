"""JeeLink receiver device — pipeline helpers.

Provides the helper functions used by the ``@app.device`` receiver
registered in :mod:`jeelink2mqtt.main`.  The receiver manages the
JeeLink adapter lifecycle and routes incoming frames through the
**filter → calibrate → publish** pipeline.

Helper functions are module-level so they can be imported directly
by the composition root and by tests.
"""

from __future__ import annotations

import json
import logging
import warnings
from datetime import UTC, datetime

import cosalette
from cosalette import DeviceStore

from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorReading
from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import SharedState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------


def _apply_pipeline(
    reading: SensorReading,
    config: SensorConfig,
    state: SharedState,
) -> SensorReading:
    """Filter → calibrate a raw reading, returning a new SensorReading.

    DEPRECATED: This function is kept for backward compatibility.
    New code should call state.apply_pipeline(reading, config) directly.
    """
    warnings.warn(
        "_apply_pipeline() is deprecated; call state.apply_pipeline(reading, config) directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    return state.apply_pipeline(reading, config)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _restore_registry(
    store: DeviceStore,
    state: SharedState,
    settings: Jeelink2MqttSettings,
) -> None:
    """Restore persisted registry state from the device store.

    DEPRECATED: This function is kept for backward compatibility.
    New code should call state.restore_from(store, settings) directly.
    """
    warnings.warn(
        "_restore_registry() is deprecated; call state.restore_from(store, settings) directly.",
        DeprecationWarning,
        stacklevel=2,
    )
    state.restore_from(store, settings)


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
    """Publish a mapping change event (non-retained).

    DEPRECATED: This function is kept for backward compatibility.
    New code should call state methods that handle event publishing directly.
    """
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
    """Publish current mapping state snapshot (retained).

    DEPRECATED: This function is kept for backward compatibility.
    New code should call state methods that handle state publishing directly.
    """
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

        last_time = state.last_publish_time.get(name)
        if last_time is None or (now - last_time).total_seconds() < interval:
            continue

        # Re-publish last known calibrated reading if available
        last = state.last_readings.get(name)
        if last is not None:
            await _publish_sensor(ctx, name, last)

        await ctx.publish(f"{name}/availability", "online", retain=True)
        state.last_publish_time[name] = now
