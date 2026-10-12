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

"""Domain error types for vito2mqtt.

Every domain-specific exception inherits from :class:`VitoBridgeError` so
callers can catch the entire family with a single ``except`` clause.

:data:`error_type_map` maps each concrete error type to a short string key
suitable for use with cosalette's :class:`~cosalette.ErrorPublisher`.
"""

from __future__ import annotations

import cosalette


class VitoBridgeError(Exception):
    """Root error for all vito2mqtt domain exceptions."""


class OptolinkConnectionError(VitoBridgeError):
    """Serial port unreachable or failed to open."""


class OptolinkTimeoutError(VitoBridgeError):
    """Device did not respond within the expected timeout."""


class InvalidSignalError(VitoBridgeError):
    """Unknown or unregistered signal name."""


class CommandNotWritableError(VitoBridgeError):
    """Attempt to write a read-only signal."""


error_type_map: dict[type[Exception], str] = {
    VitoBridgeError: "vito_bridge",
    OptolinkConnectionError: "optolink_connection",
    OptolinkTimeoutError: "optolink_timeout",
    InvalidSignalError: "invalid_signal",
    CommandNotWritableError: "command_not_writable",
}

disclose_messages_for: frozenset[type[Exception]] = (
    cosalette.FRAMEWORK_DISCLOSED_ERRORS | frozenset(error_type_map)
)
"""Exception types whose message is published on the error topic (cosalette ADR-091).

The domain errors above carry sanitised messages, and the framework's own
rejection errors (bad JSON, unknown sub-command, invalid payload) are sanitised
by cosalette. Every other exception publishes its class name only.

The builtin ``TimeoutError`` stays out on purpose, so a watchdog timeout
publishes ``error_type`` ``timeout`` with the message ``TimeoutError``. Libraries
raise ``TimeoutError`` too, with text that can name hosts or addresses, and the
label already says what happened.
"""
