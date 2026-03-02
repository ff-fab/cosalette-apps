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

"""Fake Optolink adapter for dry-run mode and testing.

:class:`FakeOptolinkAdapter` implements :class:`~vito2mqtt.ports.OptolinkPort`
without any hardware dependency.  It returns configurable or sensible
default values for every signal, and tracks writes for test assertions.

This adapter is ideal for:
- **Dry-run mode**: Verify the full pipeline without hardware.
- **Integration tests**: Inject known responses to test higher layers.
- **Development**: Work on MQTT publishing without a boiler.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.errors import CommandNotWritableError, InvalidSignalError
from vito2mqtt.optolink.codec import CycleTimeSchedule, ReturnStatus
from vito2mqtt.optolink.commands import COMMANDS, AccessMode

# ---------------------------------------------------------------------------
# Default value factories per type code
# ---------------------------------------------------------------------------


def _default_es(language: str) -> list[Any]:
    """Default ES (error history) value — no error with a fixed timestamp."""
    label = (
        "Regelbetrieb (kein Fehler)"
        if language == "de"
        else "normal operation (no error)"
    )
    return [label, datetime(2026, 1, 1)]


def _default_ct() -> CycleTimeSchedule:
    """Default CT (cycle time) — empty schedule with all slots unset."""
    return [
        [[None, None], [None, None]],
        [[None, None], [None, None]],
        [[None, None], [None, None]],
        [[None, None], [None, None]],
    ]


_DEFAULTS_SIMPLE: dict[str, Any] = {
    "IS10": 20.5,
    "IUNON": 42,
    "IU3600": 1.5,
    "PR2": 128,
    "PR3": 50.0,
    "RT": ReturnStatus.OFF,
}

_DEFAULTS_LANG: dict[str, dict[str, Any]] = {
    "BA": {"en": "shutdown", "de": "Abschaltbetrieb"},
    "USV": {"en": "undefined", "de": "undefiniert"},
}


def _get_default(type_code: str, language: str) -> Any:
    """Return a sensible default value for a given type code.

    Args:
        type_code: One of the 11 supported codec type codes.
        language: ``"en"`` or ``"de"``.

    Returns:
        A representative default value matching the type.
    """
    if type_code in _DEFAULTS_SIMPLE:
        return _DEFAULTS_SIMPLE[type_code]

    if type_code in _DEFAULTS_LANG:
        return _DEFAULTS_LANG[type_code].get(language, _DEFAULTS_LANG[type_code]["en"])

    if type_code == "ES":
        return _default_es(language)

    if type_code == "CT":
        return _default_ct()

    if type_code == "TI":
        return datetime.now()  # noqa: DTZ005

    # Fallback for unknown type codes — should not happen with valid commands
    return None  # pragma: no cover


# ---------------------------------------------------------------------------
# FakeOptolinkAdapter
# ---------------------------------------------------------------------------


class FakeOptolinkAdapter:
    """In-memory fake implementing :class:`~vito2mqtt.ports.OptolinkPort`.

    Returns configurable responses for reads and tracks write calls.
    Validates signal names and access modes exactly like the real adapter.

    Args:
        settings: Optional application settings.  If provided, the
            ``signal_language`` is used for language-dependent defaults.
        responses: Optional mapping of signal name → fixed return value.
            Takes precedence over type-based defaults.
    """

    def __init__(
        self,
        settings: Vito2MqttSettings | None = None,
        *,
        responses: dict[str, Any] | None = None,
    ) -> None:
        self._language: str = settings.signal_language if settings else "en"
        self._responses: dict[str, Any] = dict(responses) if responses else {}
        self.writes: dict[str, Any] = {}

    # -- async context manager (protocol compatibility) ---------------------

    async def __aenter__(self) -> FakeOptolinkAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    # -- OptolinkPort implementation ----------------------------------------

    async def read_signal(self, name: str) -> Any:
        """Return a configured or default value for *name*.

        Args:
            name: Signal identifier (must exist in ``COMMANDS``).

        Returns:
            Configured response or a sensible type-based default.

        Raises:
            InvalidSignalError: If *name* is not in the command registry.
        """
        cmd = self._lookup(name)
        if cmd.access_mode == AccessMode.WRITE:
            msg = f"Signal {name!r} is write-only"
            raise InvalidSignalError(msg)

        if name in self._responses:
            return self._responses[name]

        return _get_default(cmd.type_code, self._language)

    async def write_signal(self, name: str, value: Any) -> None:
        """Record the write in :attr:`writes`.

        Validates that the signal exists and is writable.

        Args:
            name: Signal identifier.
            value: Value to "write" (stored in ``self.writes``).

        Raises:
            InvalidSignalError: If *name* is not in the command registry.
            CommandNotWritableError: If the signal is read-only.
        """
        cmd = self._lookup(name)
        if cmd.access_mode == AccessMode.READ:
            msg = f"Signal {name!r} is read-only"
            raise CommandNotWritableError(msg)
        self.writes[name] = value

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        """Batch-read multiple signals.

        Args:
            names: Sequence of signal identifiers.

        Returns:
            Mapping of signal name → value.
        """
        results: dict[str, Any] = {}
        for name in names:
            results[name] = await self.read_signal(name)
        return results

    # -- private helpers ----------------------------------------------------

    @staticmethod
    def _lookup(name: str) -> Any:
        """Look up a command by signal name.

        Raises:
            InvalidSignalError: If *name* is not in the registry.
        """
        cmd = COMMANDS.get(name)
        if cmd is None:
            msg = f"Unknown signal: {name!r}"
            raise InvalidSignalError(msg)
        return cmd
