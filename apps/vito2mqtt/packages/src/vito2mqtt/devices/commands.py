# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Command handler registration for writable signal groups.

Registers one command handler per writable domain group with the cosalette
application.  Each handler listens on ``{prefix}/{device_id}/{group}/set``
for incoming JSON payloads, validates the signal names, deserializes
values, and dispatches ``write_signal()`` calls to the Optolink port.

Architecture
------------
``register_commands(app)`` iterates over :data:`COMMAND_GROUPS` and calls
``app.add_command()`` for each group.  Handler closures are created via
the factory function ``_make_handler(group)`` to avoid the classic
late-binding closure pitfall.

Read-Before-Write
-----------------
For READ_WRITE signals the handler batch-reads current boiler values
before writing.  If a value is unchanged, the write is skipped — this
reduces serial bus traffic and avoids unnecessary EEPROM wear on the
boiler controller.  The ``__force`` meta-key in the JSON payload bypasses
the comparison and writes unconditionally.

Eventual Consistency
--------------------
Command handlers return ``None`` — state is published by telemetry
polling, not by command confirmation.  After a write, the next telemetry
cycle picks up the changed value.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from cosalette import App

from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices import COMMAND_GROUPS
from vito2mqtt.devices._serialization import deserialize_value, serialize_value
from vito2mqtt.errors import InvalidSignalError
from vito2mqtt.optolink.commands import COMMANDS, AccessMode
from vito2mqtt.ports import OptolinkPort

__all__ = ["register_commands"]


def _parse_payload(raw: str, group: str) -> tuple[dict[str, Any], bool]:
    """Parse JSON, extract ``__force`` meta-key, and validate signal names.

    Splits the raw JSON string into validated signal data and the
    ``__force`` flag in one step.  Unknown signal names (other than
    ``__force``) raise :class:`InvalidSignalError`.

    Args:
        raw: Raw JSON string from the MQTT message.
        group: Command group name for validation context.

    Returns:
        Tuple of ``(data, force)`` where *data* contains only signal
        keys and *force* is the boolean meta-flag.

    Raises:
        InvalidSignalError: If the payload is not valid JSON, is not a
            dict, or contains unknown signal names.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON payload for group {group!r}: {exc}"
        raise InvalidSignalError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Expected JSON object for group {group!r}, got {type(data).__name__}"
        raise InvalidSignalError(msg)

    # Extract meta-key before validation — __force is not a signal name
    raw_force = data.pop("__force", False)
    if not isinstance(raw_force, bool):
        msg = f"'__force' must be a JSON boolean, got {type(raw_force).__name__}"
        raise InvalidSignalError(msg)
    force = raw_force

    allowed = set(COMMAND_GROUPS[group])
    unknown = set(data.keys()) - allowed
    if unknown:
        msg = (
            f"Unknown signal(s) in group {group!r}: "
            f"{', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
        raise InvalidSignalError(msg)

    return data, force


def _validate_payload(raw: str, group: str) -> dict[str, Any]:
    """Parse and validate a JSON command payload.

    Thin wrapper around :func:`_parse_payload` that discards the
    ``__force`` meta-key — kept for backward compatibility.

    Args:
        raw: Raw JSON string from the MQTT message.
        group: Command group name for validation context.

    Returns:
        Parsed dict with validated signal names.

    Raises:
        InvalidSignalError: If the payload is not valid JSON or
            contains unknown signal names.
    """
    data, _force = _parse_payload(raw, group)
    return data


def _make_handler(
    group: str,
) -> Callable[..., Awaitable[dict[str, object] | None]]:
    """Create an async command handler closure for a signal group.

    The factory pattern avoids the late-binding closure pitfall — each
    handler captures its own *group* value at creation time.

    Args:
        group: Command group name (key in :data:`COMMAND_GROUPS`).

    Returns:
        Async callable suitable for ``app.add_command(func=...)``.
    """

    async def handler(payload: str, port: OptolinkPort) -> dict[str, object] | None:
        data, force = _parse_payload(payload, group)
        if not data:
            return None

        # Batch-read current values for comparison (READ_WRITE signals only)
        current_values: dict[str, object] = {}
        if not force:
            readable_names = [
                n for n in data if COMMANDS[n].access_mode == AccessMode.READ_WRITE
            ]
            if readable_names:
                current_values = await port.read_signals(readable_names)

        for name, value in data.items():
            type_code = COMMANDS[name].type_code
            deserialized = deserialize_value(value, type_code)

            if not force and name in current_values:
                current_serialized = serialize_value(current_values[name], type_code)
                if current_serialized == value:
                    continue  # Skip write — value unchanged

            await port.write_signal(name, deserialized)

        return None

    return handler


def register_commands(app: App) -> None:
    """Register command handlers for all writable signal groups.

    Creates one command handler per group defined in
    :data:`~vito2mqtt.devices.COMMAND_GROUPS`.

    Args:
        app: The cosalette application instance.  Must have been
            constructed with ``settings_class=Vito2MqttSettings``.
    """
    settings = app.settings
    if not isinstance(settings, Vito2MqttSettings):
        msg = (
            f"Expected Vito2MqttSettings, got {type(settings).__name__}. "
            "Ensure App was constructed with settings_class=Vito2MqttSettings."
        )
        raise TypeError(msg)

    for group_name in COMMAND_GROUPS:
        app.add_command(
            name=group_name,
            func=_make_handler(group_name),
        )
