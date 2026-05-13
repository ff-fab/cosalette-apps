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

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import cosalette
from cosalette import DeviceStore, StreamablePort
from cosalette.stores import JsonFileStore

from jeelink2mqtt import __version__
from jeelink2mqtt import commands as _commands
from jeelink2mqtt import receiver as _receiver
from jeelink2mqtt.adapters import FakeJeeLinkAdapter, PyLaCrosseAdapter
from jeelink2mqtt.models import SensorReading
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
    adapters={StreamablePort[SensorReading]: (_make_adapter, FakeJeeLinkAdapter)},
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


@app.stream(
    summary="JeeLink LaCrosse serial receiver: read sensor frames and publish state",
)
async def receiver(  # pragma: no cover — composition root, tested via integration
    stream: cosalette.Stream[SensorReading],
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> AsyncIterator[None]:
    """Main receiver loop: read frames from stream, process, publish."""

    # -- Restore persisted registry state (if any) -------------------------
    state.restore_from(store, settings)

    logger.info("Receiver started — listening on %s", settings.serial_port)
    last_persist_time = datetime.now(UTC)

    try:
        async for reading in stream:
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
                    state.record_published_reading(name, calibrated, datetime.now(UTC))
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

            yield

    finally:
        for sensor_cfg in settings.sensors:
            await ctx.publish(f"{sensor_cfg.name}/availability", "offline", retain=True)
        logger.info("Receiver stopped")


@app.device(
    "staleness",
    summary="Staleness checker: publish offline availability for stale sensors",
)
async def staleness(  # pragma: no cover — composition root, tested via helpers
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> AsyncIterator[None]:
    """Periodic staleness check: mark sensors offline if no recent readings."""
    while not ctx.shutdown_requested:
        await ctx.sleep(1.0)
        await _receiver._check_staleness(ctx, settings, state)
        yield


@app.device(
    "heartbeat",
    summary="Heartbeat publisher: re-publish sensor state at configured interval",
)
async def heartbeat(  # pragma: no cover — composition root, tested via helpers
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> AsyncIterator[None]:
    """Periodic heartbeat: re-publish last known readings to prevent inactivity timeouts.

    Checks every 1 second for eligible sensors (matching the old receiver loop cadence),
    while _maybe_heartbeat uses settings.heartbeat_interval_seconds as the threshold.
    """
    while not ctx.shutdown_requested:
        await ctx.sleep(1.0)
        await _receiver._maybe_heartbeat(ctx, settings, state)
        yield


_PARSE_OR_ERROR_IMPOSSIBLE: str = "_parse_or_error returned (None, None)"
"""
Invariant guard message: _parse_or_error always returns (data, None) or (None, err),
never (None, None). Both mapping_assign and mapping_reset reference this constant so
the message stays in sync across sites.
"""


def _parse_or_error(
    payload: str,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Parse a mapping command payload or return an error response dict.

    Returns:
        ``(parsed_data, None)`` on success.
        ``(None, {"error": ...})`` on parse failure.
    """
    try:
        return _commands.parse_command_payload(payload), None
    except _commands.MappingCommandPayloadError as exc:
        return None, {"error": str(exc)}


@app.command(
    "mapping",
    sub="assign",
    summary="Manually assign an ephemeral sensor ID to a logical name",
)
async def mapping_assign(
    payload: str,
    store: DeviceStore,
    state: SharedState,
) -> dict[str, object]:
    """Assign a sensor ID to a named sensor.

    Payload: {"command": "assign", "sensor_name": "office", "sensor_id": 42}
    """
    data, err = _parse_or_error(payload)
    if err is not None:
        return err
    if data is None:  # invariant: err is None ⟹ data is not None
        raise RuntimeError(_PARSE_OR_ERROR_IMPOSSIBLE)

    result = _commands.handle_assign(state, data)

    if "error" not in result:
        store["registry"] = state.registry.to_dict()

    return result


@app.command(
    "mapping",
    sub="reset",
    summary="Remove the mapping for a named sensor",
)
async def mapping_reset(
    payload: str,
    store: DeviceStore,
    state: SharedState,
) -> dict[str, object]:
    """Reset (remove) the mapping for a named sensor.

    Payload: {"command": "reset", "sensor_name": "office"}
    """
    data, err = _parse_or_error(payload)
    if err is not None:
        return err
    if data is None:  # invariant: err is None ⟹ data is not None
        raise RuntimeError(_PARSE_OR_ERROR_IMPOSSIBLE)

    result = _commands.handle_reset(state, data)

    if "error" not in result:
        store["registry"] = state.registry.to_dict()

    return result


@app.command(
    "mapping",
    sub="reset_all",
    summary="Clear all sensor mappings",
)
async def mapping_reset_all(
    payload: str,
    store: DeviceStore,
    state: SharedState,
) -> dict[str, object]:
    """Clear all sensor mappings.

    Payload: {"command": "reset_all"}
    """
    _, err = _parse_or_error(payload)
    if err is not None:
        return err

    result = _commands.handle_reset_all(state)

    store["registry"] = state.registry.to_dict()

    return result


@app.command(
    "mapping",
    sub="list_unknown",
    summary="Return recently-seen sensor IDs that are not yet mapped",
)
async def mapping_list_unknown(
    payload: str,  # noqa: ARG001 — framework requires; list_unknown needs no payload fields
    store: DeviceStore,  # noqa: ARG001 — Required by cosalette command DI; list_unknown is read-only
    state: SharedState,
) -> dict[str, object]:
    """List unmapped sensor IDs.

    Payload: {"command": "list_unknown"}

    Note: Does not persist anything to the store.
    """
    return _commands.handle_list_unknown(state)


def main() -> None:
    """Start the application."""
    app.run()
