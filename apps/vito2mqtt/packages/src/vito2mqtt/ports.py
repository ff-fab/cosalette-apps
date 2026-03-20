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

"""Port interfaces (Dependency Inversion boundary).

:class:`OptolinkPort` defines the contract between the application layer
and the adapter layer.  Concrete adapters implement this protocol; the
application layer depends only on the protocol — never on a specific
adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OptolinkPort(Protocol):
    """Async interface for reading and writing Optolink signals.

    This is a :pep:`544` structural-subtyping protocol.  Any class that
    implements the three methods below satisfies the protocol without
    explicit inheritance.
    """

    async def read_signal(self, name: str) -> Any:
        """Read a single signal by name.

        Args:
            name: The signal identifier (e.g. ``"outdoor_temp"``).

        Returns:
            The decoded signal value.
        """
        ...

    async def write_signal(self, name: str, value: Any) -> None:
        """Write a single signal.

        Args:
            name: The signal identifier.
            value: The value to write (must match the signal's type).
        """
        ...

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        """Batch-read multiple signals.

        Args:
            names: Sequence of signal identifiers to read.

        Returns:
            Mapping of signal name → decoded value.
        """
        ...
