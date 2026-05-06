"""MQTT command implementations for sensor mapping management.

Provides the command handler functions used by the ``@app.command``
mapping sub-command handlers registered in :mod:`jeelink2mqtt.main`.

Commands are dispatched by cosalette via MQTT sub-topic routing
(``command`` field in payload maps to a registered sub-command)::

    jeelink2mqtt/mapping/set  ← incoming command payload
    jeelink2mqtt/mapping/state ← handler response
    jeelink2mqtt/mapping/error ← framework-level routing errors

Sub-commands::

    {"command": "assign",       "sensor_name": "office", "sensor_id": 42}
    {"command": "reset",        "sensor_name": "office"}
    {"command": "reset_all"}
    {"command": "list_unknown"}

.. note::

   Events are NOT drained here — the receiver loop is the single owner
   of ``drain_events()``, ensuring ``mapping/event`` publication and
   filter cleanup happen in one place.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from jeelink2mqtt.errors import MappingConflictError
from jeelink2mqtt.state import SharedState

logger = logging.getLogger(__name__)


class MappingCommandPayloadError(Exception):
    """Raised when a mapping command payload cannot be parsed or is invalid."""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def parse_command_payload(payload: str) -> dict[str, object]:
    """Parse and validate JSON command payload.

    Returns:
        Parsed data dict on success.

    Raises:
        MappingCommandPayloadError: If parsing fails or payload is invalid.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid JSON in mapping command: %d bytes, error at position %d",
            len(payload),
            exc.pos,
        )
        raise MappingCommandPayloadError("Invalid JSON payload") from exc

    if not isinstance(data, dict):
        logger.warning(
            "Non-object JSON in mapping command: %d bytes, type=%s",
            len(payload),
            type(data).__name__,
        )
        raise MappingCommandPayloadError("JSON payload must be an object")

    return data


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def handle_assign(
    state: SharedState,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Manually assign an ephemeral sensor ID to a logical name."""
    sensor_name = data.get("sensor_name")
    sensor_id = data.get("sensor_id")

    if not sensor_name or sensor_id is None:
        return {"error": "assign requires 'sensor_name' and 'sensor_id'"}

    if not isinstance(sensor_id, int) or isinstance(sensor_id, bool):
        return {"error": "sensor_id must be an integer"}

    try:
        event = state.registry.assign(str(sensor_name), sensor_id)
    except MappingConflictError as exc:
        logger.debug("Mapping conflict for sensor_id=%d: %s", sensor_id, exc)
        return {"error": "sensor ID already assigned"}
    except ValueError as exc:
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


def handle_reset(
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


def handle_reset_all(
    state: SharedState,
) -> dict[str, Any]:
    """Clear all sensor mappings."""
    events = state.registry.reset_all()
    return {
        "status": "ok",
        "cleared": len(events),
        "sensors": [e.sensor_name for e in events],
    }


def handle_list_unknown(
    state: SharedState,
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
