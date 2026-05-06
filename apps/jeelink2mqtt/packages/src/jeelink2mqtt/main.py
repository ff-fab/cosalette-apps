"""jeelink2mqtt application entry point.

Wires the cosalette App with the JeeLink USB receiver adapter, shared
state lifespan, and MQTT command handler.  The ``main()`` function is
the CLI entry point.

Topic layout::

    jeelink2mqtt/{sensor_name}/state      ← calibrated readings
    jeelink2mqtt/{sensor_name}/availability
    jeelink2mqtt/raw/state                ← every decoded frame
    jeelink2mqtt/mapping/state            ← current ID→name map
    jeelink2mqtt/mapping/event            ← mapping change events
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cosalette
from cosalette import DeviceStore
from cosalette.stores import JsonFileStore

from jeelink2mqtt import __version__
from jeelink2mqtt import commands as _commands
from jeelink2mqtt import receiver as _receiver
from jeelink2mqtt.adapters import FakeJeeLinkAdapter, PyLaCrosseAdapter
from jeelink2mqtt.ports import JeeLinkPort
from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import SharedState, build_shared_state

logger = logging.getLogger(__name__)


def _make_adapter(settings: Jeelink2MqttSettings) -> PyLaCrosseAdapter:
    """Factory for the production JeeLink adapter."""
    return PyLaCrosseAdapter(port=settings.serial_port, baud_rate=settings.baud_rate)


app = cosalette.App(
    name="jeelink2mqtt",
    version=__version__,
    description="JeeLink LaCrosse sensor bridge for MQTT",
    settings_class=Jeelink2MqttSettings,
    store=JsonFileStore(Path("data") / "jeelink2mqtt.json"),
    adapters={JeeLinkPort: (_make_adapter, FakeJeeLinkAdapter)},
)


@app.state
def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    """State factory for SharedState with registry, filter bank, and sensor configs."""
    state = build_shared_state(settings)
    logger.info(
        "Shared state ready — %d sensor(s): %s",
        len(state.sensor_configs),
        ", ".join(state.sensor_configs.keys()) or "(none)",
    )
    return state


@app.device(
    summary="JeeLink LaCrosse serial receiver: read sensor frames and publish state",
)
async def receiver(  # pragma: no cover — composition root, tested via integration
    ctx: cosalette.DeviceContext,
    jeelink: JeeLinkPort,
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """Main receiver loop: open adapter, read frames, process, publish."""

    # -- Restore persisted registry state (if any) -------------------------
    state.restore_from(store, settings)

    # -- Open adapter and start scanning ------------------------------------
    async with jeelink:
        logger.info("Receiver started — listening on %s", settings.serial_port)

        last_persist_time = datetime.now(UTC)

        try:
            while not ctx.shutdown_requested:
                try:
                    # Use timeout to allow prompt shutdown checking
                    reading = await asyncio.wait_for(anext(jeelink), timeout=1.0)
                except TimeoutError:
                    # No reading within timeout — loop continues for shutdown check
                    continue
                except StopAsyncIteration:
                    # Iterator exhausted (adapter closed)
                    logger.info("JeeLink iterator exhausted — receiver ending")
                    break

                # 1. Raw diagnostic (every frame, non-retained)
                await _receiver._publish_raw(ctx, reading)

                # 2. Route through registry
                name = state.registry.record_reading(reading)

                # 3. Mapped → filter → calibrate → publish
                if name is not None:
                    config = state.sensor_configs.get(name)
                    if config is not None:
                        calibrated = state.apply_pipeline(reading, config)
                        await _receiver._publish_sensor(ctx, name, calibrated)
                        state.record_published_reading(
                            name, calibrated, datetime.now(UTC)
                        )
                        await ctx.publish(f"{name}/availability", "online", retain=True)

                # 4. Mapping events (only publish state when something changed)
                if await state.flush_events(ctx, store):
                    last_persist_time = datetime.now(UTC)

                # 5. Periodic persistence for last_seen metadata (ADR-004)
                now = datetime.now(UTC)
                new_persist_time = state.persist_registry_if_due(
                    store, now, last_persist_time, 60
                )
                if new_persist_time is not None:
                    last_persist_time = new_persist_time

        finally:
            for sensor_cfg in settings.sensors:
                await ctx.publish(
                    f"{sensor_cfg.name}/availability", "offline", retain=True
                )
            logger.info("Receiver stopped")


@app.device(
    "staleness",
    summary="Staleness checker: publish offline availability for stale sensors",
)
async def staleness(  # pragma: no cover — composition root, tested via helpers
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """Periodic staleness check: mark sensors offline if no recent readings."""
    while not ctx.shutdown_requested:
        await ctx.sleep(1.0)
        await _receiver._check_staleness(ctx, settings, state)


@app.device(
    "heartbeat",
    summary="Heartbeat publisher: re-publish sensor state at configured interval",
)
async def heartbeat(  # pragma: no cover — composition root, tested via helpers
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """Periodic heartbeat: re-publish last known readings to prevent inactivity timeouts.

    Checks every 1 second for eligible sensors (matching the old receiver loop cadence),
    while _maybe_heartbeat uses settings.heartbeat_interval_seconds as the threshold.
    """
    while not ctx.shutdown_requested:
        await ctx.sleep(1.0)
        await _receiver._maybe_heartbeat(ctx, settings, state)


@app.command(
    "mapping",
    summary="Map a raw sensor ID to a named sensor",
)
async def handle_mapping(
    payload: str,
    store: DeviceStore,
    state: SharedState,
) -> dict[str, object] | None:
    """Route an incoming mapping command to the correct handler.

    Supported commands::

        {"command": "assign",       "sensor_name": "office", "sensor_id": 42}
        {"command": "reset",        "sensor_name": "office"}
        {"command": "reset_all"}
        {"command": "list_unknown"}

    Mutations (assign, reset, reset_all) immediately persist the
    registry to the device store, ensuring changes survive restarts.
    Returns a response dict that cosalette publishes to
    ``jeelink2mqtt/mapping/state``, or ``None`` on no-op.
    """
    import json

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in mapping command: %r", payload)
        return {"error": "Invalid JSON payload"}

    if not isinstance(data, dict):
        logger.warning("Non-object JSON in mapping command: %r", payload)
        return {"error": "JSON payload must be an object"}

    command = data.get("command", "")

    _handlers: dict[str, Any] = {
        "assign": _commands._handle_assign,
        "reset": _commands._handle_reset,
        "reset_all": _commands._handle_reset_all,
        "list_unknown": _commands._handle_list_unknown,
    }

    handler = _handlers.get(command)
    if handler is None:
        logger.warning("Unknown mapping command: %r", command)
        return {"error": f"Unknown command: {command}"}

    result = handler(state, data)

    if command in {"assign", "reset", "reset_all"}:
        store["registry"] = state.registry.to_dict()

    return result


def main() -> None:
    """Start the application."""
    app.run()
