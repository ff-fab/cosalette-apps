"""JeeLink receiver device — pipeline helpers.

Provides the helper functions used by the ``@app.stream`` receiver and
the per-sensor ``sensor_entity`` device, both registered in
:mod:`jeelink2mqtt.main`. The stream manages the JeeLink adapter
lifecycle and routes incoming frames through the **filter → calibrate
→ cache** pipeline; each configured sensor's own ``sensor_entity``
device (:func:`sensor_entity_tick`) publishes the cached reading,
handles heartbeat re-publish, and owns availability.

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
# Per-sensor device tick (state publish + heartbeat + staleness/availability)
# ---------------------------------------------------------------------------


async def sensor_entity_tick(
    ctx: cosalette.DeviceContext,
    name: str,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """One tick of a per-sensor ``sensor_entity`` device (see main.py).

    Unifies what were three separate publish paths — immediate state,
    global staleness sweep, global heartbeat sweep — into a single
    per-sensor check:

    1. Stale (no raw frame within the staleness timeout): mark
       unavailable once, on the fresh→stale transition.
    2. Not stale: mark available once, on recovery, then publish state
       if the stream cached a reading newer than our last publish, or
       if the heartbeat interval has elapsed since our last publish.
    """
    if state.registry.is_stale(name):
        if state.last_availability.get(name) != "offline":
            await ctx.mark_unavailable()
            state.last_availability[name] = "offline"
        return

    if state.last_availability.get(name) != "online":
        await ctx.mark_available()
        state.last_availability[name] = "online"

    reading = state.last_readings.get(name)
    if reading is None:
        return

    now = datetime.now(UTC)
    last_publish = state.last_publish_time.get(name)
    reading_at = state.last_reading_at.get(name)
    is_fresh = last_publish is None or (
        reading_at is not None and reading_at > last_publish
    )
    is_heartbeat_due = (
        last_publish is not None
        and (now - last_publish).total_seconds() >= settings.heartbeat_interval_seconds
    )

    if not (is_fresh or is_heartbeat_due):
        return

    await ctx.publish_state(
        {
            "temperature": round(reading.temperature, 2),
            "humidity": reading.humidity,
            "low_battery": reading.low_battery,
            "timestamp": reading.timestamp.isoformat(),
        }
    )
    state.last_publish_time[name] = now
