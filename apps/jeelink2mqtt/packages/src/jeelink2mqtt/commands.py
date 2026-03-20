"""MQTT command handler for sensor mapping management.

Listens on ``jeelink2mqtt/mapping/set`` and dispatches JSON commands
to the shared :class:`~jeelink2mqtt.registry.SensorRegistry`.

Supported commands::

    {"command": "assign",       "sensor_name": "office", "sensor_id": 42}
    {"command": "reset",        "sensor_name": "office"}
    {"command": "reset_all"}
    {"command": "list_unknown"}

When the handler returns a ``dict``, cosalette auto-publishes it
as the device state → ``jeelink2mqtt/mapping/state``.

.. note::

   The receiver also publishes a retained mapping **snapshot** to
   ``mapping/state``.  Command responses follow a different schema
   (``{status, event}``); the receiver's next snapshot will overwrite
   the command response, restoring the canonical schema.

Events are NOT drained by the command handler — the receiver loop
is the single owner of ``drain_events()``, ensuring ``mapping/event``
publication and filter cleanup happen in one place.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import cosalette
from cosalette import DeviceStore

from jeelink2mqtt.app import SharedState, get_state
from jeelink2mqtt.errors import MappingConflictError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_commands(app: cosalette.App) -> None:
    """Register the mapping command handler on *app*."""

    @app.command("mapping")
    async def handle_mapping(
        payload: str,
        store: DeviceStore,
    ) -> dict[str, object] | None:
        """Route an incoming mapping command to the correct handler.

        Mutations (assign, reset, reset_all) immediately persist the
        registry to the device store and drain events, ensuring
        changes survive restarts without waiting for the next reading.

        Returns a response ``dict`` that cosalette auto-publishes
        to ``jeelink2mqtt/mapping/state``, or ``None`` on no-op.
        """
        state = get_state()

        try:
            data: dict[str, Any] = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in mapping command: %r", payload)
            return {"error": "Invalid JSON payload"}

        command = data.get("command", "")

        _handlers: dict[
            str,
            Callable[[SharedState, dict[str, Any]], dict[str, object]],
        ] = {
            "assign": _handle_assign,
            "reset": _handle_reset,
            "reset_all": _handle_reset_all,
            "list_unknown": _handle_list_unknown,
        }

        handler = _handlers.get(command)
        if handler is None:
            logger.warning("Unknown mapping command: %r", command)
            return {"error": f"Unknown command: {command}"}

        result = handler(state, data)

        # Persist immediately after mutation so the mapping survives a
        # crash.  Events are NOT drained here — the receiver loop is
        # the single owner of drain_events(), ensuring mapping/event
        # publication and filter cleanup happen in one place.
        if command in {"assign", "reset", "reset_all"}:
            store["registry"] = state.registry.to_dict()

        return result


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _handle_assign(
    state: SharedState,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Manually assign an ephemeral sensor ID to a logical name."""
    sensor_name = data.get("sensor_name")
    sensor_id = data.get("sensor_id")

    if not sensor_name or sensor_id is None:
        return {"error": "assign requires 'sensor_name' and 'sensor_id'"}

    try:
        event = state.registry.assign(str(sensor_name), int(sensor_id))
    except (MappingConflictError, ValueError) as exc:
        return {"error": str(exc)}

    return {
        "status": "ok",
        "event": {
            "event_type": event.event_type,
            "sensor_name": event.sensor_name,
            "old_sensor_id": event.old_sensor_id,
            "new_sensor_id": event.new_sensor_id,
            "reason": event.reason,
        },
    }


def _handle_reset(
    state: SharedState,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Remove the mapping for a named sensor."""
    sensor_name = data.get("sensor_name")
    if not sensor_name:
        return {"error": "reset requires 'sensor_name'"}

    event = state.registry.reset(str(sensor_name))
    if event is None:
        return {"status": "ok", "message": f"No mapping existed for '{sensor_name}'"}

    return {
        "status": "ok",
        "event": {
            "event_type": event.event_type,
            "sensor_name": event.sensor_name,
            "old_sensor_id": event.old_sensor_id,
        },
    }


def _handle_reset_all(
    state: SharedState,
    data: dict[str, Any],  # noqa: ARG001
) -> dict[str, Any]:
    """Clear all sensor mappings."""
    events = state.registry.reset_all()
    return {
        "status": "ok",
        "cleared": len(events),
        "sensors": [e.sensor_name for e in events],
    }


def _handle_list_unknown(
    state: SharedState,
    data: dict[str, Any],  # noqa: ARG001
) -> dict[str, Any]:
    """Return recently-seen sensor IDs that are not yet mapped."""
    unmapped = state.registry.get_unmapped_ids()
    return {
        "status": "ok",
        "unknown_sensors": {
            str(sid): {
                "temperature": r.temperature,
                "humidity": r.humidity,
                "low_battery": r.low_battery,
                "timestamp": r.timestamp.isoformat(),
            }
            for sid, r in unmapped.items()
        },
    }
