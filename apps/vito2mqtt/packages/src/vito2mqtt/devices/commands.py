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
from vito2mqtt.devices._serialization import deserialize_value
from vito2mqtt.errors import InvalidSignalError
from vito2mqtt.optolink.commands import COMMANDS
from vito2mqtt.ports import OptolinkPort

__all__ = ["register_commands"]


def _validate_payload(raw: str, group: str) -> dict[str, Any]:
    """Parse and validate a JSON command payload.

    Args:
        raw: Raw JSON string from the MQTT message.
        group: Command group name for validation context.

    Returns:
        Parsed dict with validated signal names.

    Raises:
        InvalidSignalError: If the payload is not valid JSON or
            contains unknown signal names.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        msg = f"Invalid JSON payload for group {group!r}: {exc}"
        raise InvalidSignalError(msg) from exc

    if not isinstance(data, dict):
        msg = f"Expected JSON object for group {group!r}, got {type(data).__name__}"
        raise InvalidSignalError(msg)

    allowed = set(COMMAND_GROUPS[group])
    unknown = set(data.keys()) - allowed
    if unknown:
        msg = (
            f"Unknown signal(s) in group {group!r}: "
            f"{', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )
        raise InvalidSignalError(msg)

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
        data = _validate_payload(payload, group)
        if not data:
            return None

        for name, value in data.items():
            type_code = COMMANDS[name].type_code
            deserialized = deserialize_value(value, type_code)
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
