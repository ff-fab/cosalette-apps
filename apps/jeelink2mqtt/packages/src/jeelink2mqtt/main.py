"""jeelink2mqtt application entry point.

Wires the cosalette App with the JeeLink USB receiver adapter, shared
state lifespan, and MQTT command handler.  The ``main()`` function is
the CLI entry point.

Topic layout::

    jeelink2mqtt/{sensor_name}/state         ← calibrated readings (per-sensor device)
    jeelink2mqtt/{sensor_name}/availability  ← framework-managed (per-sensor device)
    jeelink2mqtt/raw/state                   ← every decoded frame
    jeelink2mqtt/mapping/state               ← current ID→name map
    jeelink2mqtt/mapping/event               ← mapping change events

Each configured sensor is registered as its own ``@app.device`` entity
(a callable ``NameSpec`` keyed by ``settings.sensors`` — see
``sensor_entity`` below); the ``receiver`` stream only decodes frames,
resolves them through the registry, and caches the calibrated reading
for the sensor's device to publish (cap-ayy).
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
from jeelink2mqtt import pipeline as _pipeline
from jeelink2mqtt import receiver as _receiver
from jeelink2mqtt.adapters import FakeJeeLinkAdapter, PyLaCrosseAdapter
from jeelink2mqtt.errors import error_type_map
from jeelink2mqtt.models import MappingEvent, SensorReading, SensorStateModel
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import SharedState, build_shared_state_logged

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
    error_type_map=error_type_map,
    restart_after_failures=5,
    max_restarts=3,
)


@app.state
def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    """State factory for SharedState with registry, filter bank, and sensor configs."""
    return build_shared_state_logged(settings)


def _persist_registry(store: DeviceStore, state: SharedState) -> None:
    """Write the current registry snapshot to the device store.

    Called by both the event-driven reactor (:func:`on_registry_events`) and
    the mapping command handlers (:func:`mapping_assign`, :func:`mapping_reset`,
    :func:`mapping_reset_all`).  The periodic writer
    (:meth:`~jeelink2mqtt.state.SharedState.persist_registry_if_due`) handles
    background persistence and is a separate code path.
    """
    store["registry"] = state.registry.to_dict()


@app.react(SharedState, drain=lambda state: state.registry.drain_events())
async def on_registry_events(
    events: list[MappingEvent],
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    state: SharedState,
) -> None:
    """Reactor for registry mapping events: publish MQTT updates and persist.

    Event-driven persistence writer — called by the framework after each
    device yield when :meth:`~jeelink2mqtt.registry.SensorRegistry.drain_events`
    returns non-empty.  See also
    :meth:`~jeelink2mqtt.state.SharedState.persist_registry_if_due` for the
    periodic background writer.
    """
    for event in events:
        await _receiver.publish_mapping_event(ctx, event)
        if event.old_sensor_id is not None:
            state.filter_bank.reset(event.old_sensor_id)

    await _receiver.publish_mapping_state(ctx, state)
    _persist_registry(store, state)


@app.stream(
    summary="JeeLink LaCrosse serial receiver: read sensor frames and publish state",
)
async def receiver(  # pragma: no cover — composition root, tested via integration
    stream: cosalette.Stream[SensorReading],
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
    notify: cosalette.EntityNotifier,
) -> AsyncIterator[None]:
    """Main receiver loop: read frames from stream, process, publish."""

    # -- Restore persisted registry state (if any) -------------------------
    state.restore_from(store, settings)

    logger.info("Receiver started — listening on %s", settings.serial_port)
    last_persist_time = datetime.now(UTC)

    try:
        async for reading in stream:
            # 1. Raw diagnostic (every frame, non-retained)
            await _receiver.publish_raw_diagnostic(ctx, reading)

            # 2. Route through registry
            name = state.registry.record_reading(reading)

            # 3. Mapped → filter → calibrate → cache
            if name is not None:
                config = state.sensor_configs.get(name)
                if config is not None:
                    calibrated = _pipeline.filter_and_calibrate(
                        reading, config, state.filter_bank
                    )
                    # Cache the calibrated reading, then wake the sensor's
                    # own device (sensor_entity) to publish it.  The arm is
                    # the freshness signal: sensor_entity_tick publishes iff
                    # it was triggered (or the heartbeat is due), so the
                    # cache write must happen first.
                    state.record_calibrated_reading(name, calibrated)
                    notify(name)

            # 4. Periodic persistence for last_seen metadata (ADR-004)
            new_persist_time = state.persist_registry_if_due(
                store, datetime.now(UTC), last_persist_time, 60
            )
            if new_persist_time is not None:
                last_persist_time = new_persist_time

            yield

    finally:
        logger.info("Receiver stopped")


_TICK_INTERVAL_SECONDS: float = 1.0
"""Heartbeat bound on :meth:`cosalette.DeviceTrigger.wait`.

Deliberately unchanged from the pre-trigger ``ctx.sleep(1.0)``: a wake only
arrives when a *frame* does, and the whole point of the remaining timeout is
the paths a frame never drives — staleness (``staleness_timeout_seconds``,
default 600 s) and the heartbeat re-publish (``heartbeat_interval_seconds``,
default 180 s).  Both are resolved to the granularity of this bound, so
lengthening it would trade a silent staleness-detection regression for
sleeps that are already free.
"""


@app.device(
    name=lambda s: {sc.name: sc for sc in s.sensors},
    summary=(
        "Per-sensor state publisher: calibrated readings, heartbeat "
        "re-publish, and staleness availability"
    ),
    state_model=SensorStateModel,
    # cosalette ADR-065: "local" is the only source a device accepts, and it
    # requires the DeviceTrigger parameter below.  The stream receiver arms
    # this entity after caching a calibrated reading.
    #
    # No min_interval=: with a throttle set, a "scheduled" payload no longer
    # means "no reading arrived" (DeviceTrigger.wait docstring), which is
    # exactly how the tick reads it.  Frame rate is bounded by the hardware
    # anyway — a LaCrosse sensor transmits every ~30 s.
    triggerable="local",
)
async def sensor_entity(  # pragma: no cover — composition root, tested via helpers
    ctx: cosalette.DeviceContext,
    config: SensorConfigSettings,
    settings: Jeelink2MqttSettings,
    state: SharedState,
    trigger: cosalette.DeviceTrigger,
) -> AsyncIterator[None]:
    """Per-configured-sensor device: publish state, heartbeat, availability.

    One instance is registered per ``settings.sensors`` entry (dict-name
    ``NameSpec``). Runs when the stream receiver caches a reading for this
    sensor, and otherwise every :data:`_TICK_INTERVAL_SECONDS` so the
    heartbeat and staleness paths still fire while the hardware is quiet;
    see :func:`jeelink2mqtt.receiver.sensor_entity_tick` for the unified
    publish/heartbeat/staleness logic.
    """
    while not ctx.shutdown_requested:
        payload = await trigger.wait(timeout=_TICK_INTERVAL_SECONDS)
        await _receiver.sensor_entity_tick(
            ctx, config.name, settings, state, triggered=payload.is_triggered
        )
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
        _persist_registry(store, state)

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
        _persist_registry(store, state)

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

    _persist_registry(store, state)

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
