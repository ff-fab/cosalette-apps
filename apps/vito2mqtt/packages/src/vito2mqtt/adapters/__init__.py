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

"""Adapter implementations for vito2mqtt port interfaces."""

from __future__ import annotations

from vito2mqtt.errors import InvalidSignalError
from vito2mqtt.optolink.commands import COMMANDS, Command

__all__ = ["lookup_command"]


def lookup_command(name: str) -> Command:
    """Resolve a signal *name* to its :class:`Command` or raise.

    Shared utility used by all adapter implementations to validate and
    retrieve a command from the registry.

    Args:
        name: Signal identifier (must exist in ``COMMANDS``).

    Returns:
        The matching :class:`Command` instance.

    Raises:
        InvalidSignalError: If *name* is not in the command registry.
    """
    cmd = COMMANDS.get(name)
    if cmd is None:
        msg = f"Unknown signal: {name!r}"
        raise InvalidSignalError(msg)
    return cmd
