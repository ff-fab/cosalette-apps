"""JeeLink receiver device — pipeline helpers.

Provides the helper functions used by the ``@app.stream`` receiver
registered in :mod:`jeelink2mqtt.main`.  The receiver manages the
JeeLink adapter lifecycle and routes incoming frames through the
**filter → calibrate → publish** pipeline.

Helper functions are module-level so they can be imported directly
by the composition root and by tests.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import cosalette

from jeelink2mqtt.models import MappingEvent, SensorReading
from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import SharedState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Publishing helpers
# ---------------------------------------------------------------------------


async def publish_raw_diagnostic(
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


async def publish_sensor_state(
    ctx: cosalette.DeviceContext,
    name: str,
    reading: SensorReading,
) -> None:
    """Publish calibrated sensor state (temperature, humidity, battery, timestamp) for a named sensor (retained)."""
    payload = json.dumps(
        {
            "temperature": round(reading.temperature, 2),
            "humidity": reading.humidity,
            "low_battery": reading.low_battery,
            "timestamp": reading.timestamp.isoformat(),
        }
    )
    await ctx.publish(f"{name}/state", payload, retain=True)


async def publish_availability(
    ctx: cosalette.DeviceContext,
    name: str,
    status: str,
) -> None:
    """Publish sensor availability status (retained).

    Args:
        name: Sensor name used in topic ``{name}/availability``.
        status: ``"online"`` or ``"offline"``.
    """
    await ctx.publish(f"{name}/availability", status, retain=True)


async def publish_mapping_event(
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


async def publish_mapping_state(
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
    """Publish ``offline`` availability for sensors that just became stale.

    Only publishes on the fresh→stale transition to avoid flooding the
    broker with duplicate retained messages.  Re-checks staleness after
    each ``await`` to guard against TOCTOU with the receiver task.
    """
    for sensor_cfg in settings.sensors:
        name = sensor_cfg.name
        if not state.registry.is_stale(name):
            continue
        if state.last_availability.get(name) == "offline":
            continue  # already offline — no duplicate publish
        await ctx.publish(f"{name}/availability", "offline", retain=True)
        # Re-validate: if the receiver processed a fresh reading while the
        # publish was in flight, correct the availability.
        if state.registry.is_stale(name):
            state.last_availability[name] = "offline"
        else:
            await ctx.publish(f"{name}/availability", "online", retain=True)


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
            await publish_sensor_state(ctx, name, last)

        await ctx.publish(f"{name}/availability", "online", retain=True)
        # Guard: only advance timestamp if receiver hasn't already updated it
        # during the above awaits (TOCTOU guard for concurrent device tasks).
        if state.last_publish_time.get(name) is last_time:
            state.last_publish_time[name] = now
