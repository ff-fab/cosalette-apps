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

"""P300 telegram framing: encode, decode, and checksum computation.

The P300 protocol uses a binary telegram format::

    0x41 | len | type | mode | addr_hi | addr_lo | data_len | [payload] | csum

Where checksum is the sum of bytes from length through payload, mod 256.

References:
    ADR-004 — Optolink Protocol Design
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

START_BYTE: int = 0x41
"""P300 telegram start byte."""

MIN_TELEGRAM_LENGTH: int = 8
"""Minimum telegram: start + len + type + mode + addr(2) + dlen + csum."""


class P300Type(IntEnum):
    """Telegram type field values."""

    REQUEST = 0x00
    RESPONSE = 0x01
    ERROR = 0x03


class P300Mode(IntEnum):
    """Telegram mode field values."""

    READ = 0x01
    WRITE = 0x02
    FUNCTION_CALL = 0x07


class TelegramError(Exception):
    """Raised for malformed or invalid telegrams."""


# ---------------------------------------------------------------------------
# Decoded telegram (immutable data object)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DecodedTelegram:
    """Parsed P300 telegram fields."""

    telegram_type: P300Type
    mode: P300Mode
    address: int
    data_length: int
    payload: bytes


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------


def checksum(data: bytes) -> int:
    """Compute P300 checksum: sum of all bytes, modulo 256.

    Args:
        data: Bytes *after* the start byte and *before* the checksum
            byte. For a full telegram ``[0x41, len, ..., payload]``,
            pass everything from ``len`` through ``payload``
            (i.e. ``telegram[1:-1]``).

    Returns:
        Single-byte checksum value (0--255).
    """
    return sum(data) % 256


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def encode_read_request(*, address: int, data_length: int) -> bytes:
    """Encode a P300 read-data request telegram.

    Args:
        address: 2-byte memory address on the boiler controller.
        data_length: Number of bytes expected in the response payload.

    Returns:
        Complete telegram bytes including start byte and checksum.
    """
    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF

    # Body: type + mode + addr_hi + addr_lo + data_length = 5 bytes
    body = bytes(
        [
            0x05,  # length of body (always 5 for read request)
            P300Type.REQUEST,
            P300Mode.READ,
            addr_hi,
            addr_lo,
            data_length,
        ]
    )
    return bytes([START_BYTE]) + body + bytes([checksum(body)])


def encode_write_request(*, address: int, payload: bytes) -> bytes:
    """Encode a P300 write-data request telegram.

    Args:
        address: 2-byte memory address on the boiler controller.
        payload: Data bytes to write (must not be empty).

    Returns:
        Complete telegram bytes including start byte and checksum.

    Raises:
        TelegramError: If payload is empty.
    """
    if not payload:
        raise TelegramError("Cannot encode write request with empty payload")

    addr_hi = (address >> 8) & 0xFF
    addr_lo = address & 0xFF
    data_length = len(payload)

    # length = type(1) + mode(1) + addr(2) + dlen(1) + payload(N)
    length = 5 + data_length

    body = (
        bytes(
            [
                length,
                P300Type.REQUEST,
                P300Mode.WRITE,
                addr_hi,
                addr_lo,
                data_length,
            ]
        )
        + payload
    )

    return bytes([START_BYTE]) + body + bytes([checksum(body)])


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def decode_telegram(raw: bytes) -> DecodedTelegram:
    """Decode a raw P300 telegram into its constituent fields.

    Validates the start byte and checksum. Works for both request and
    response telegrams.

    Args:
        raw: Complete telegram bytes including start byte and checksum.

    Returns:
        Parsed telegram as a ``DecodedTelegram`` dataclass.

    Raises:
        TelegramError: On invalid start byte, checksum mismatch,
            or structurally invalid telegram (too short, etc.).
    """
    if len(raw) < MIN_TELEGRAM_LENGTH:
        raise TelegramError(
            f"Telegram too short: {len(raw)} bytes (minimum {MIN_TELEGRAM_LENGTH})"
        )

    if raw[0] != START_BYTE:
        raise TelegramError(
            f"Invalid start byte: 0x{raw[0]:02X} (expected 0x{START_BYTE:02X})"
        )

    # Body is everything between start byte and checksum
    body = raw[1:-1]
    expected_csum = checksum(body)
    actual_csum = raw[-1]

    if actual_csum != expected_csum:
        raise TelegramError(
            f"Checksum mismatch: got 0x{actual_csum:02X}, "
            f"expected 0x{expected_csum:02X}"
        )

    # Validate length field matches actual frame size.
    # Expected total: start(1) + len_byte(1) + body[0] content + checksum(1)
    expected_total = body[0] + 3
    if len(raw) != expected_total:
        raise TelegramError(
            f"Length mismatch: header says {expected_total} bytes, got {len(raw)}"
        )

    # Parse fields from body
    try:
        telegram_type = P300Type(body[1])
        mode = P300Mode(body[2])
    except ValueError as exc:
        raise TelegramError(f"Unknown telegram field value: {exc}") from exc
    addr_hi = body[3]
    addr_lo = body[4]
    address = (addr_hi << 8) | addr_lo
    data_length = body[5]

    # Payload starts at body[6] and runs for data_length bytes
    # For read requests, data_length indicates *expected* response
    # size, and there is no actual payload in the request telegram
    payload_bytes = body[6:]

    return DecodedTelegram(
        telegram_type=telegram_type,
        mode=mode,
        address=address,
        data_length=data_length,
        payload=bytes(payload_bytes),
    )
