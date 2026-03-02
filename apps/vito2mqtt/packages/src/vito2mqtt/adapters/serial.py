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

"""Real Optolink adapter — connects to the boiler via serial P300 protocol.

:class:`OptolinkAdapter` implements :class:`~vito2mqtt.ports.OptolinkPort`
using the optolink sub-package for serial communication.  Each signal
read/write opens a fresh serial connection, performs the P300 handshake,
executes the command, and closes — a *connect-per-cycle* strategy that
keeps the serial port available between polling intervals.

An :class:`asyncio.Lock` serializes concurrent access so only one
coroutine talks to the hardware at a time.

References:
    ADR-003 — Hardware Abstraction
    ADR-004 — Optolink Protocol Design
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.errors import (
    CommandNotWritableError,
    InvalidSignalError,
    OptolinkConnectionError,
    OptolinkTimeoutError,
)
from vito2mqtt.optolink import codec
from vito2mqtt.optolink.commands import COMMANDS, AccessMode
from vito2mqtt.optolink.transport import DeviceError, P300Session

# ---------------------------------------------------------------------------
# StreamReader/StreamWriter → SerialPort adapter
# ---------------------------------------------------------------------------


class _AsyncSerialPort:
    """Adapts :mod:`asyncio` stream objects to the :class:`SerialPort` protocol.

    Bridges ``serial_asyncio.open_serial_connection`` (which returns a
    ``StreamReader``/``StreamWriter`` pair) to the ``SerialPort`` protocol
    expected by :class:`P300Session`.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def read(self, n: int) -> bytes:
        """Read exactly *n* bytes from the serial stream."""
        return await self._reader.readexactly(n)

    async def write(self, data: bytes) -> None:
        """Write *data* to the serial stream and flush."""
        self._writer.write(data)
        await self._writer.drain()

    async def close(self) -> None:
        """Close the underlying writer (and its transport)."""
        self._writer.close()
        await self._writer.wait_closed()


# ---------------------------------------------------------------------------
# OptolinkAdapter
# ---------------------------------------------------------------------------


class OptolinkAdapter:
    """Real adapter for Optolink serial communication.

    Implements :class:`~vito2mqtt.ports.OptolinkPort` via structural
    subtyping — no explicit inheritance required.

    Args:
        settings: Application settings providing serial port path,
            baud rate, and signal language.
    """

    def __init__(self, settings: Vito2MqttSettings) -> None:
        self._serial_port = settings.serial_port
        self._baud_rate = settings.serial_baud_rate
        self._language = settings.signal_language
        self._lock = asyncio.Lock()

    # -- async context manager (no-op, connect-per-cycle) -------------------

    async def __aenter__(self) -> OptolinkAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass  # connect-per-cycle — nothing to tear down

    # -- OptolinkPort implementation ----------------------------------------

    async def read_signal(self, name: str) -> Any:
        """Read a single signal by name.

        Opens a serial session, reads raw bytes from the boiler,
        and decodes them using the codec.

        Args:
            name: Signal identifier (must exist in ``COMMANDS``).

        Returns:
            Decoded signal value.

        Raises:
            InvalidSignalError: If *name* is not in the command registry.
            OptolinkConnectionError: On serial or device errors.
            OptolinkTimeoutError: If the device does not respond in time.
        """
        cmd = self._lookup(name)
        if cmd.access_mode == AccessMode.WRITE:
            msg = f"Signal {name!r} is write-only"
            raise InvalidSignalError(msg)

        async with self._lock, self._open_session() as session:
            raw = await session.read(cmd.address, cmd.length)

        return codec.decode(cmd.type_code, raw, language=self._language)

    async def write_signal(self, name: str, value: Any) -> None:
        """Write a value to a single signal.

        Args:
            name: Signal identifier (must exist in ``COMMANDS``).
            value: Value to encode and write.

        Raises:
            InvalidSignalError: If *name* is not in the command registry.
            CommandNotWritableError: If the signal is read-only.
            OptolinkConnectionError: On serial or device errors.
            OptolinkTimeoutError: If the device does not respond in time.
        """
        cmd = self._lookup(name)
        if cmd.access_mode == AccessMode.READ:
            msg = f"Signal {name!r} is read-only"
            raise CommandNotWritableError(msg)

        encoded = codec.encode(
            cmd.type_code,
            value,
            language=self._language,
            byte_length=cmd.length,
        )

        async with self._lock, self._open_session() as session:
            await session.write(cmd.address, encoded)

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        """Batch-read multiple signals.

        Iterates over *names* and calls :meth:`read_signal` for each.

        Args:
            names: Sequence of signal identifiers.

        Returns:
            Mapping of signal name → decoded value.
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

    @asynccontextmanager
    async def _open_session(self) -> AsyncIterator[P300Session]:
        """Open a serial connection and yield a P300 session.

        Uses ``serial_asyncio`` (lazy-imported) to open the serial port,
        wraps the streams in :class:`_AsyncSerialPort`, and enters a
        :class:`P300Session` context.  Translates transport-level
        exceptions into domain errors.

        Yields:
            An initialized :class:`P300Session` ready for read/write.

        Raises:
            OptolinkConnectionError: On serial open failure or device error.
            OptolinkTimeoutError: On timeout waiting for device response.
        """
        try:
            import serial_asyncio  # lazy import — unavailable in test/dry-run

            reader, writer = await serial_asyncio.open_serial_connection(
                url=self._serial_port,
                baudrate=self._baud_rate,
            )
        except (OSError, ImportError) as exc:
            msg = f"Failed to open serial port {self._serial_port!r}: {exc}"
            raise OptolinkConnectionError(msg) from exc

        port = _AsyncSerialPort(reader, writer)
        try:
            async with P300Session(port) as session:
                yield session
        except DeviceError as exc:
            msg = f"Device communication error: {exc}"
            raise OptolinkConnectionError(msg) from exc
        except TimeoutError as exc:
            msg = f"Timeout communicating with device: {exc}"
            raise OptolinkTimeoutError(msg) from exc
