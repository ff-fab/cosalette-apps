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

"""P300 session controller: handshake and read/write orchestration.

Handles the P300 initialization sequence (reset/sync/ACK exchange) and
orchestrates read/write requests over the serial link.  Raises
``DeviceError`` on communication failures or error responses.

This is the top layer of the optolink sub-package and deals exclusively
in raw bytes — the caller is responsible for encoding/decoding typed
values via ``codec`` and resolving signal names via ``commands``.

References:
    ADR-004 — Optolink Protocol Design
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

from vito2mqtt.optolink import telegram
from vito2mqtt.optolink.telegram import P300Mode, P300Type

# ---------------------------------------------------------------------------
# P300 control codes
# ---------------------------------------------------------------------------

RESET: Final[bytes] = b"\x04"
"""Reset interface to a known state."""

SYNC: Final[bytes] = b"\x16\x00\x00"
"""Enter P300 mode (synchronisation trigger)."""

ACK: Final[bytes] = b"\x06"
"""Acknowledgement — sent and received to confirm operations."""

NOT_INIT: Final[bytes] = b"\x05"
"""Interface is powered up but not yet initialised."""

ERROR: Final[bytes] = b"\x15"
"""Interface-level error indicator."""


# ---------------------------------------------------------------------------
# Serial port abstraction
# ---------------------------------------------------------------------------


@runtime_checkable
class SerialPort(Protocol):
    """Abstract byte-level serial I/O — injectable for testing.

    Implementations must return *exactly* ``n`` bytes from :meth:`read`
    or raise an exception (e.g. ``TimeoutError``, ``OSError``).  Partial
    reads are not supported by the P300 session controller.
    """

    async def read(self, n: int) -> bytes: ...
    async def write(self, data: bytes) -> None: ...
    async def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class DeviceError(Exception):
    """Raised when the boiler returns an error or communication fails."""


# ---------------------------------------------------------------------------
# P300 session
# ---------------------------------------------------------------------------


class P300Session:
    """Async context manager for P300 protocol sessions.

    Performs the P300 initialization handshake on entry, provides
    :meth:`read` / :meth:`write` methods for boiler memory access,
    and closes the underlying serial port on exit.

    Usage::

        async with P300Session(serial_port) as session:
            data = await session.read(0x0800, 2)
            await session.write(0x6300, b"\\x2d")
    """

    def __init__(self, port: SerialPort, *, max_init_retries: int = 10) -> None:
        self._port = port
        self._max_init_retries = max_init_retries

    # -- context manager ----------------------------------------------------

    async def __aenter__(self) -> P300Session:
        try:
            await self._initialize()
        except Exception:
            await self._port.close()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._port.close()

    # -- public API ---------------------------------------------------------

    async def read(self, address: int, length: int) -> bytes:
        """Read *length* bytes from boiler memory at *address*.

        Returns the raw payload bytes from the response telegram.

        Raises:
            DeviceError: On communication failure or error response.
        """
        telegram_bytes = telegram.encode_read_request(
            address=address, data_length=length
        )
        await self._port.write(telegram_bytes)
        await self._wait_for_ack("read")

        response_bytes = await self._port.read(8 + length)
        decoded = telegram.decode_telegram(response_bytes)

        if decoded.telegram_type == P300Type.ERROR:
            raise DeviceError("error response from device")
        if decoded.telegram_type != P300Type.RESPONSE:
            raise DeviceError(f"unexpected response type: {decoded.telegram_type!r}")
        self._validate_echo(decoded, P300Mode.READ, address, length)

        await self._port.write(ACK)
        return decoded.payload

    async def write(self, address: int, payload: bytes) -> None:
        """Write *payload* bytes to boiler memory at *address*.

        Raises:
            DeviceError: On communication failure or error response.
        """
        telegram_bytes = telegram.encode_write_request(address=address, payload=payload)
        await self._port.write(telegram_bytes)
        await self._wait_for_ack("write")

        response_bytes = await self._port.read(8 + len(payload))
        decoded = telegram.decode_telegram(response_bytes)

        if decoded.telegram_type == P300Type.ERROR:
            raise DeviceError("error response from device")
        if decoded.telegram_type != P300Type.RESPONSE:
            raise DeviceError(f"unexpected response type: {decoded.telegram_type!r}")
        self._validate_echo(decoded, P300Mode.WRITE, address, len(payload))

        await self._port.write(ACK)

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _validate_echo(
        decoded: telegram.DecodedTelegram,
        expected_mode: P300Mode,
        expected_address: int,
        expected_data_length: int,
    ) -> None:
        """Verify the response echoes the request's mode, address, and data_length.

        Catches stale or out-of-order responses that are structurally valid
        but don't correspond to the current request.

        Raises:
            DeviceError: If any echo field doesn't match.
        """
        mismatches: list[str] = []
        if decoded.mode != expected_mode:
            mismatches.append(f"mode={decoded.mode!r} (expected {expected_mode!r})")
        if decoded.address != expected_address:
            mismatches.append(
                f"address=0x{decoded.address:04X} (expected 0x{expected_address:04X})"
            )
        if decoded.data_length != expected_data_length:
            mismatches.append(
                f"data_length={decoded.data_length} (expected {expected_data_length})"
            )
        if mismatches:
            raise DeviceError(f"response echo mismatch: {', '.join(mismatches)}")

    async def _initialize(self) -> None:
        """Run the P300 initialization handshake.

        Repeatedly reads single bytes from the port, responding with
        SYNC when the interface reports NOT_INIT or RESET on any other
        state, until an ACK is received.

        Raises:
            DeviceError: If the handshake doesn't complete within
                *max_init_retries* attempts.
        """
        for _ in range(self._max_init_retries):
            byte = await self._port.read(1)
            if byte == ACK:
                return
            if byte == NOT_INIT:
                await self._port.write(SYNC)
            else:
                await self._port.write(RESET)
        raise DeviceError(
            f"initialization failed after {self._max_init_retries} attempts"
        )

    async def _wait_for_ack(self, operation: str) -> None:
        """Read an ACK byte, retrying once on failure.

        Raises:
            DeviceError: If no ACK received after a single retry.
        """
        ack = await self._port.read(1)
        if ack != ACK:
            ack = await self._port.read(1)
            if ack != ACK:
                raise DeviceError(f"no ACK after {operation} request")
