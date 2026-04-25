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
from jeelink2mqtt.app import _lifespan
from jeelink2mqtt.models import SensorReading
from jeelink2mqtt.ports import JeeLinkPort
from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import SharedState

logger = logging.getLogger(__name__)


def _make_adapter(settings: Jeelink2MqttSettings) -> PyLaCrosseAdapter:
    """Factory for the production JeeLink adapter."""
    return PyLaCrosseAdapter(port=settings.serial_port, baud_rate=settings.baud_rate)


app = cosalette.App(
    name="jeelink2mqtt",
    version=__version__,
    description="JeeLink LaCrosse sensor bridge for MQTT",
    settings_class=Jeelink2MqttSettings,
    lifespan=_lifespan,
    store=JsonFileStore(Path("data") / "jeelink2mqtt.json"),
    adapters={JeeLinkPort: (_make_adapter, FakeJeeLinkAdapter)},
)


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
    _receiver._restore_registry(store, state, settings)

    # -- Bridge sync callbacks → async queue --------------------------------
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

    last_readings: dict[str, SensorReading] = {}
    last_publish_time: dict[str, datetime] = {}
    last_persist_time = datetime.now(UTC)

    try:
        while not ctx.shutdown_requested:
            try:
                reading = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                await _receiver._check_staleness(ctx, settings, state)
                await _receiver._maybe_heartbeat(
                    ctx, settings, state, last_readings, last_publish_time
                )
                continue

            # 1. Raw diagnostic (every frame, non-retained)
            await _receiver._publish_raw(ctx, reading)

            # 2. Route through registry
            name = state.registry.record_reading(reading)

            # 3. Mapped → filter → calibrate → publish
            if name is not None:
                config = state.sensor_configs.get(name)
                if config is not None:
                    calibrated = _receiver._apply_pipeline(reading, config, state)
                    await _receiver._publish_sensor(ctx, name, calibrated)
                    last_readings[name] = calibrated
                    last_publish_time[name] = datetime.now(UTC)
                    await ctx.publish(f"{name}/availability", "online", retain=True)

            # 4. Mapping events (only publish state when something changed)
            events = state.registry.drain_events()
            for event in events:
                await _receiver._publish_mapping_event(ctx, event)
                if event.old_sensor_id is not None:
                    state.filter_bank.reset(event.old_sensor_id)

            if events:
                await _receiver._publish_mapping_state(ctx, state)
                store["registry"] = state.registry.to_dict()
                last_persist_time = datetime.now(UTC)

            # 5. Periodic persistence for last_seen metadata (ADR-004)
            now = datetime.now(UTC)
            if (now - last_persist_time).total_seconds() >= 60:
                store["registry"] = state.registry.to_dict()
                last_persist_time = now

    finally:
        for sensor_cfg in settings.sensors:
            await ctx.publish(f"{sensor_cfg.name}/availability", "offline", retain=True)
        jeelink.stop_scan()
        jeelink.close()
        logger.info("Receiver stopped")


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
        data: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in mapping command: %r", payload)
        return {"error": "Invalid JSON payload"}

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
