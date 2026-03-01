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

"""Unit tests for optolink/telegram.py — P300 telegram framing.

Test Techniques Used:
- Specification-based: Verify telegram structure matches P300 protocol spec
- Round-trip Testing: encode → decode fidelity
- Boundary Value Analysis: Min/max payload sizes, address boundaries
- Equivalence Partitioning: Request types (read/write), response types
- Error Guessing: Invalid checksums, missing start byte, truncated telegrams
"""

from __future__ import annotations

import pytest

from vito2mqtt.optolink.telegram import (
    P300Mode,
    P300Type,
    TelegramError,
    checksum,
    decode_telegram,
    encode_read_request,
    encode_write_request,
)

# ---------------------------------------------------------------------------
# Checksum computation
# ---------------------------------------------------------------------------


class TestChecksum:
    """Checksum is sum of all bytes from length through payload, mod 256."""

    def test_checksum_simple_read_request(self) -> None:
        """Known example from P300 spec: read 0x5525, 2 bytes.

        Payload after start byte: 05 00 01 55 25 02
        Sum: 5+0+1+85+37+2 = 130 = 0x82

        Technique: Specification-based — known protocol example.
        """
        data = bytes([0x05, 0x00, 0x01, 0x55, 0x25, 0x02])
        assert checksum(data) == 0x82

    def test_checksum_response_with_payload(self) -> None:
        """Known example: response to 0x5525 read, value 0x00EF (23.9°C).

        Payload after start byte: 07 01 01 55 25 02 EF 00
        Sum: 7+1+1+85+37+2+239+0 = 372 = 0x174 → 0x74

        Technique: Specification-based — known protocol example.
        """
        data = bytes([0x07, 0x01, 0x01, 0x55, 0x25, 0x02, 0xEF, 0x00])
        assert checksum(data) == 0x74

    def test_checksum_wraps_at_256(self) -> None:
        """Checksum wraps modulo 256.

        Technique: Boundary Value Analysis — overflow boundary.
        """
        # 0xFF + 0x01 = 256 → wraps to 0
        data = bytes([0xFF, 0x01])
        assert checksum(data) == 0x00

    def test_checksum_empty_data(self) -> None:
        """Empty data produces checksum 0.

        Technique: Boundary Value Analysis — empty input.
        """
        assert checksum(b"") == 0x00

    def test_checksum_single_byte(self) -> None:
        """Single byte returns itself.

        Technique: Boundary Value Analysis — minimal input.
        """
        assert checksum(bytes([0x42])) == 0x42


# ---------------------------------------------------------------------------
# Encode read request
# ---------------------------------------------------------------------------


class TestEncodeReadRequest:
    """Encode a P300 read request telegram."""

    def test_encode_read_request_known_example(self) -> None:
        """Read 2 bytes from address 0x5525.

        Expected: 41 05 00 01 55 25 02 82

        Technique: Specification-based — known protocol example.
        """
        telegram = encode_read_request(address=0x5525, data_length=2)
        assert telegram == bytes([0x41, 0x05, 0x00, 0x01, 0x55, 0x25, 0x02, 0x82])

    def test_encode_read_request_single_byte(self) -> None:
        """Read 1 byte from address 0x2323 (BA operating mode).

        Technique: Equivalence Partitioning — single-byte read.
        """
        telegram = encode_read_request(address=0x2323, data_length=1)
        # Verify structure
        assert telegram[0] == 0x41  # start byte
        assert telegram[1] == 0x05  # length: type(1) + mode(1) + addr(2) + dlen(1) = 5
        assert telegram[2] == 0x00  # type: request
        assert telegram[3] == 0x01  # mode: read
        assert telegram[4] == 0x23  # address high
        assert telegram[5] == 0x23  # address low
        assert telegram[6] == 0x01  # data_length
        # Checksum: 5+0+1+0x23+0x23+1 = 5+0+1+35+35+1 = 77 = 0x4D
        assert telegram[7] == 0x4D

    def test_encode_read_request_max_address(self) -> None:
        """Read from address 0xFFFF — maximum 2-byte address.

        Technique: Boundary Value Analysis — max address value.
        """
        telegram = encode_read_request(address=0xFFFF, data_length=1)
        assert telegram[4] == 0xFF
        assert telegram[5] == 0xFF

    def test_encode_read_request_zero_address(self) -> None:
        """Read from address 0x0000 — minimum address.

        Technique: Boundary Value Analysis — min address value.
        """
        telegram = encode_read_request(address=0x0000, data_length=1)
        assert telegram[4] == 0x00
        assert telegram[5] == 0x00

    def test_encode_read_request_length_field(self) -> None:
        """Length byte counts: type + mode + addr_hi + addr_lo + data_len = 5.

        Technique: Specification-based — fixed structure for read requests.
        """
        telegram = encode_read_request(address=0x0808, data_length=2)
        assert telegram[1] == 0x05  # always 5 for read requests

    def test_encode_read_request_8_bytes(self) -> None:
        """Read 8 bytes (e.g., cycle time CT or error set ES).

        Technique: Equivalence Partitioning — multi-byte read.
        """
        telegram = encode_read_request(address=0x2100, data_length=8)
        assert telegram[6] == 0x08
        assert len(telegram) == 8  # 1+1+1+1+2+1+1 = header(4)+addr(2)+dlen(1)+csum(1)


# ---------------------------------------------------------------------------
# Encode write request
# ---------------------------------------------------------------------------


class TestEncodeWriteRequest:
    """Encode a P300 write request telegram."""

    def test_encode_write_request_single_byte(self) -> None:
        """Write 1 byte (0x02) to address 0x2323 (set BA to Normalbetrieb).

        Technique: Specification-based — write with single-byte payload.
        """
        telegram = encode_write_request(address=0x2323, payload=bytes([0x02]))
        assert telegram[0] == 0x41  # start byte
        assert telegram[2] == 0x00  # type: request
        assert telegram[3] == 0x02  # mode: write
        assert telegram[4] == 0x23  # address high
        assert telegram[5] == 0x23  # address low
        assert telegram[6] == 0x01  # data_length = len(payload)
        assert telegram[7] == 0x02  # payload byte
        # length = type(1) + mode(1) + addr(2) + dlen(1) + payload(1) = 6
        assert telegram[1] == 0x06

    def test_encode_write_request_multi_byte(self) -> None:
        """Write 2 bytes to an address.

        Technique: Equivalence Partitioning — multi-byte write.
        """
        telegram = encode_write_request(
            address=0x6300,
            payload=bytes([0xE8, 0x03]),  # 1000 = 0x03E8 LE
        )
        assert telegram[6] == 0x02  # data_length
        assert telegram[7] == 0xE8
        assert telegram[8] == 0x03
        assert telegram[1] == 0x07  # length = 1+1+2+1+2 = 7

    def test_encode_write_request_8_byte_payload(self) -> None:
        """Write 8 bytes (e.g., cycle time CT).

        Technique: Boundary Value Analysis — large payload.
        """
        payload = bytes([0x51, 0x99, 0x51, 0x99, 0xFF, 0xFF, 0xFF, 0xFF])
        telegram = encode_write_request(address=0x2100, payload=payload)
        assert telegram[6] == 0x08  # data_length
        assert telegram[7:15] == payload
        assert telegram[1] == 0x0D  # length = 1+1+2+1+8 = 13

    def test_encode_write_request_empty_payload_raises(self) -> None:
        """Write with empty payload is invalid.

        Technique: Error Guessing — empty payload.
        """
        with pytest.raises(TelegramError, match="[Ee]mpty.*payload"):
            encode_write_request(address=0x2323, payload=b"")


# ---------------------------------------------------------------------------
# Decode telegram (response parsing)
# ---------------------------------------------------------------------------


class TestDecodeTelegram:
    """Decode a P300 response telegram from raw bytes."""

    def test_decode_read_response_known_example(self) -> None:
        """Decode known response: read 0x5525 → 0x00EF (23.9°C).

        Raw: 41 07 01 01 55 25 02 EF 00 74

        Technique: Specification-based — known protocol example.
        """
        raw = bytes([0x41, 0x07, 0x01, 0x01, 0x55, 0x25, 0x02, 0xEF, 0x00, 0x74])
        result = decode_telegram(raw)

        assert result.telegram_type == P300Type.RESPONSE
        assert result.mode == P300Mode.READ
        assert result.address == 0x5525
        assert result.data_length == 2
        assert result.payload == bytes([0xEF, 0x00])

    def test_decode_read_response_single_byte(self) -> None:
        """Decode a single-byte response (e.g., BA operating mode).

        Technique: Equivalence Partitioning — single-byte response.
        """
        # Build a valid response: address 0x2323, 1 byte payload 0x02
        body = bytes([0x06, 0x01, 0x01, 0x23, 0x23, 0x01, 0x02])
        csum = sum(body) % 256
        raw = bytes([0x41]) + body + bytes([csum])

        result = decode_telegram(raw)
        assert result.telegram_type == P300Type.RESPONSE
        assert result.mode == P300Mode.READ
        assert result.address == 0x2323
        assert result.payload == bytes([0x02])

    def test_decode_error_response(self) -> None:
        """Decode an error response (type=0x03).

        Technique: Equivalence Partitioning — error type.
        """
        # Error response: type=0x03, mode=read, address 0x5525, 0 data bytes
        body = bytes([0x05, 0x03, 0x01, 0x55, 0x25, 0x00])
        csum = sum(body) % 256
        raw = bytes([0x41]) + body + bytes([csum])

        result = decode_telegram(raw)
        assert result.telegram_type == P300Type.ERROR

    def test_decode_write_response(self) -> None:
        """Decode a write acknowledgement response.

        Technique: Equivalence Partitioning — write mode response.
        """
        body = bytes([0x05, 0x01, 0x02, 0x23, 0x23, 0x00])
        csum = sum(body) % 256
        raw = bytes([0x41]) + body + bytes([csum])

        result = decode_telegram(raw)
        assert result.telegram_type == P300Type.RESPONSE
        assert result.mode == P300Mode.WRITE
        assert result.address == 0x2323

    def test_decode_invalid_checksum_raises(self) -> None:
        """Invalid checksum raises TelegramError.

        Technique: Error Guessing — corrupted checksum.
        """
        raw = bytes([0x41, 0x07, 0x01, 0x01, 0x55, 0x25, 0x02, 0xEF, 0x00, 0xFF])
        with pytest.raises(TelegramError, match="[Cc]hecksum"):
            decode_telegram(raw)

    def test_decode_wrong_start_byte_raises(self) -> None:
        """Missing start byte 0x41 raises TelegramError.

        Technique: Error Guessing — wrong start byte.
        """
        raw = bytes([0x42, 0x07, 0x01, 0x01, 0x55, 0x25, 0x02, 0xEF, 0x00, 0x74])
        with pytest.raises(TelegramError, match="[Ss]tart byte"):
            decode_telegram(raw)

    def test_decode_truncated_telegram_raises(self) -> None:
        """Telegram shorter than minimum length raises TelegramError.

        Min: start + len + type + mode + addr(2) + dlen + csum = 8

        Technique: Boundary Value Analysis — below minimum length.
        """
        raw = bytes([0x41, 0x05, 0x00, 0x01])  # only 4 bytes
        with pytest.raises(TelegramError, match="[Tt]oo short|[Ll]ength"):
            decode_telegram(raw)

    def test_decode_request_telegram(self) -> None:
        """Decode a request telegram (type=0x00) — used for testing round-trips.

        Technique: Round-trip Testing — verify decode of encoded request.
        """
        raw = bytes([0x41, 0x05, 0x00, 0x01, 0x55, 0x25, 0x02, 0x82])
        result = decode_telegram(raw)
        assert result.telegram_type == P300Type.REQUEST
        assert result.mode == P300Mode.READ
        assert result.address == 0x5525
        assert result.data_length == 2
        assert result.payload == b""


# ---------------------------------------------------------------------------
# Round-trip: encode → decode
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Encode a telegram, then decode it — verify fidelity.

    Technique: Round-trip Testing — serialization/deserialization fidelity.
    """

    def test_roundtrip_read_request(self) -> None:
        """Encode read request, decode it back."""
        encoded = encode_read_request(address=0x5525, data_length=2)
        decoded = decode_telegram(encoded)

        assert decoded.telegram_type == P300Type.REQUEST
        assert decoded.mode == P300Mode.READ
        assert decoded.address == 0x5525
        assert decoded.data_length == 2

    def test_roundtrip_write_request(self) -> None:
        """Encode write request, decode it back — payload preserved."""
        payload = bytes([0x02])
        encoded = encode_write_request(address=0x2323, payload=payload)
        decoded = decode_telegram(encoded)

        assert decoded.telegram_type == P300Type.REQUEST
        assert decoded.mode == P300Mode.WRITE
        assert decoded.address == 0x2323
        assert decoded.payload == payload

    def test_roundtrip_write_request_multi_byte(self) -> None:
        """Round-trip with multi-byte payload."""
        payload = bytes([0xE8, 0x03])
        encoded = encode_write_request(address=0x6300, payload=payload)
        decoded = decode_telegram(encoded)

        assert decoded.mode == P300Mode.WRITE
        assert decoded.payload == payload

    @pytest.mark.parametrize(
        ("address", "data_length"),
        [
            (0x0000, 1),
            (0x5525, 2),
            (0x0808, 2),
            (0x2100, 8),
            (0xFFFF, 4),
        ],
        ids=[
            "min-address-1byte",
            "outdoor-temp-2byte",
            "flow-temp-2byte",
            "cycle-time-8byte",
            "max-address-4byte",
        ],
    )
    def test_roundtrip_read_parametrized(self, address: int, data_length: int) -> None:
        """Parametrized round-trip for various addresses and sizes."""
        encoded = encode_read_request(address=address, data_length=data_length)
        decoded = decode_telegram(encoded)

        assert decoded.address == address
        assert decoded.data_length == data_length


# ---------------------------------------------------------------------------
# Enum values
# ---------------------------------------------------------------------------


class TestEnumValues:
    """P300Type and P300Mode enum values match protocol spec.

    Technique: Specification-based — enum values match protocol constants.
    """

    def test_p300_type_values(self) -> None:
        assert P300Type.REQUEST == 0x00
        assert P300Type.RESPONSE == 0x01
        assert P300Type.ERROR == 0x03

    def test_p300_mode_values(self) -> None:
        assert P300Mode.READ == 0x01
        assert P300Mode.WRITE == 0x02
        assert P300Mode.FUNCTION_CALL == 0x07


# ---------------------------------------------------------------------------
# Length field validation
# ---------------------------------------------------------------------------


class TestLengthValidation:
    """Verify that decode_telegram validates the length field
    against the actual telegram size.

    Technique: Defense in depth — length field provides an independent
    structural check beyond the checksum.
    """

    def test_truncated_frame_with_valid_checksum_raises(self) -> None:
        """A telegram with a length field implying more bytes than present.

        We build a valid 10-byte telegram (body[0]=7) then remove one
        byte from the payload, yielding 9 bytes. The length field says
        10 but the frame is only 9 → length mismatch.

        Technique: Error Guessing — truncated serial read.
        """
        # Valid write response: 0x41 [07 01 02 55 25 02 EF 00] csum = 10 bytes
        body = bytes([0x07, 0x01, 0x02, 0x55, 0x25, 0x02, 0xEF, 0x00])
        raw_valid = bytes([0x41]) + body + bytes([checksum(body)])
        assert len(raw_valid) == 10  # sanity check

        # Truncate: remove last payload byte but recompute checksum
        truncated_body = bytes([0x07, 0x01, 0x02, 0x55, 0x25, 0x02, 0xEF])
        csum = checksum(truncated_body)
        raw_truncated = bytes([0x41]) + truncated_body + bytes([csum])
        # body[0] = 7 → expected_total = 7+3 = 10, actual = 9
        with pytest.raises(TelegramError, match="[Ll]ength mismatch"):
            decode_telegram(raw_truncated)

    def test_padded_frame_with_extra_bytes_raises(self) -> None:
        """A telegram with extra trailing bytes beyond what length says.

        Technique: Error Guessing — serial buffer contamination.
        """
        # Build valid request then append an extra byte (re-computing checksum)
        body = bytes([0x05, 0x00, 0x01, 0x55, 0x25, 0x02, 0xFF])
        raw = bytes([0x41]) + body + bytes([checksum(body)])
        # body[0] = 5 → expected total = 8, actual = 10
        with pytest.raises(TelegramError, match="[Ll]ength mismatch"):
            decode_telegram(raw)

    def test_valid_frame_passes_length_check(self) -> None:
        """A correctly formed telegram passes the length validation.

        Technique: Specification-based — positive verification.
        """
        raw = encode_read_request(address=0x5525, data_length=2)
        # Should not raise
        result = decode_telegram(raw)
        assert result.address == 0x5525


# ---------------------------------------------------------------------------
# Unknown enum field values
# ---------------------------------------------------------------------------


class TestUnknownEnumValues:
    """Verify that unknown P300Type/P300Mode values raise TelegramError.

    The enum constructors raise ValueError for invalid values, but the
    public API contract says only TelegramError escapes.

    Technique: Contract correctness — wrap internal exceptions.
    """

    def test_unknown_telegram_type_raises_telegram_error(self) -> None:
        """Unknown type byte (e.g. 0xFF) raises TelegramError, not ValueError.

        Technique: Error Guessing — corrupted type field.
        """
        # Build a frame with type=0xFF (invalid) but valid checksum
        body = bytes([0x05, 0xFF, 0x01, 0x55, 0x25, 0x02])
        raw = bytes([0x41]) + body + bytes([checksum(body)])
        with pytest.raises(TelegramError, match="Unknown telegram field"):
            decode_telegram(raw)

    def test_unknown_mode_raises_telegram_error(self) -> None:
        """Unknown mode byte (e.g. 0xAA) raises TelegramError, not ValueError.

        Technique: Error Guessing — corrupted mode field.
        """
        body = bytes([0x05, 0x01, 0xAA, 0x55, 0x25, 0x02])
        raw = bytes([0x41]) + body + bytes([checksum(body)])
        with pytest.raises(TelegramError, match="Unknown telegram field"):
            decode_telegram(raw)
