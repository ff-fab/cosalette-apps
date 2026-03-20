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

"""Unit tests for optolink/transport.py — P300 session controller.

Test Techniques Used:
- State Transition Testing: Initialization handshake FSM (NOT_INIT → SYNC → ACK)
- Specification-based: Verify control code values, protocol sequences
- Branch/Condition Coverage: ACK retry paths, error response branches
- Error Guessing: Timeout (empty reads), exhausted retries, malformed telegrams
- Equivalence Partitioning: Read vs write flows, success vs error responses
"""

from __future__ import annotations

import pytest

from vito2mqtt.optolink.telegram import (
    P300Mode,
    TelegramError,
    encode_read_request,
    encode_write_request,
)
from vito2mqtt.optolink.transport import (
    ACK,
    ERROR,
    NOT_INIT,
    RESET,
    SYNC,
    DeviceError,
    P300Session,
    SerialPort,
)

from .conftest import FakeSerial, build_response

# ---------------------------------------------------------------------------
# Control codes
# ---------------------------------------------------------------------------


class TestControlCodes:
    """Verify P300 control code constants match protocol specification.

    Technique: Specification-based — known protocol byte values.
    """

    def test_reset_value(self) -> None:
        assert RESET == b"\x04"

    def test_sync_value(self) -> None:
        assert SYNC == b"\x16\x00\x00"

    def test_ack_value(self) -> None:
        assert ACK == b"\x06"

    def test_not_init_value(self) -> None:
        assert NOT_INIT == b"\x05"

    def test_error_value(self) -> None:
        assert ERROR == b"\x15"

    def test_all_are_bytes_type(self) -> None:
        """All control codes must be bytes instances.

        Technique: Specification-based — type correctness.
        """
        for code in (RESET, SYNC, ACK, NOT_INIT, ERROR):
            assert isinstance(code, bytes)


# ---------------------------------------------------------------------------
# Initialization handshake
# ---------------------------------------------------------------------------


class TestInitHandshake:
    """Test the P300 initialization state machine.

    The handshake reads single bytes from the port and transitions:
    - NOT_INIT → send SYNC, keep trying
    - ACK → initialized (success)
    - ERROR / timeout / unknown → send RESET, keep trying

    Technique: State Transition Testing.
    """

    async def test_happy_path_not_init_then_ack(self) -> None:
        """NOT_INIT → SYNC sent → ACK → initialized.

        Technique: State Transition — nominal two-step path.
        """
        fake = FakeSerial([NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        assert SYNC in fake.written
        # Only SYNC should have been written (no RESET)
        assert fake.written == [SYNC]

    async def test_already_acked(self) -> None:
        """ACK received immediately — already initialized.

        Technique: State Transition — shortest path.
        """
        fake = FakeSerial([ACK])
        session = P300Session(fake)
        await session._initialize()

        # No writes required when already ACKed
        assert fake.written == []

    async def test_error_state_then_init(self) -> None:
        """ERROR → RESET → NOT_INIT → SYNC → ACK → success.

        Technique: State Transition — error recovery path.
        """
        fake = FakeSerial([ERROR, NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        assert fake.written == [RESET, SYNC]

    async def test_unknown_byte_sends_reset(self) -> None:
        """Unknown byte triggers RESET, then recovers via NOT_INIT → ACK.

        Technique: Error Guessing — unsupported byte value.
        """
        fake = FakeSerial([b"\xff", NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        assert fake.written == [RESET, SYNC]

    async def test_timeout_empty_read_sends_reset(self) -> None:
        """Empty read (timeout) triggers RESET, then recovers.

        Technique: Error Guessing — serial timeout.
        """
        # First read returns empty (timeout), then recovery sequence
        fake = FakeSerial([b"", NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        # Empty read → RESET, NOT_INIT → SYNC
        assert fake.written == [RESET, SYNC]

    async def test_max_retries_exhausted_raises(self) -> None:
        """DeviceError raised after max_init_retries with no ACK.

        Technique: Boundary Value Analysis — retry limit.
        """
        # All reads return NOT_INIT but never ACK — retries exhaust
        retries = 3
        fake = FakeSerial([NOT_INIT] * retries)
        session = P300Session(fake, max_init_retries=retries)

        with pytest.raises(DeviceError, match="initialization failed"):
            await session._initialize()

    async def test_multiple_error_cycles_before_success(self) -> None:
        """Several ERROR cycles before eventual NOT_INIT → ACK.

        Technique: State Transition — repeated error recovery.
        """
        fake = FakeSerial([ERROR, ERROR, ERROR, NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        assert fake.written == [RESET, RESET, RESET, SYNC]

    async def test_sync_sent_exactly_once_per_not_init(self) -> None:
        """SYNC is sent once per NOT_INIT, not more.

        Technique: Specification-based — protocol correctness.
        """
        fake = FakeSerial([NOT_INIT, NOT_INIT, ACK])
        session = P300Session(fake)
        await session._initialize()

        sync_count = sum(1 for w in fake.written if w == SYNC)
        assert sync_count == 2  # One per NOT_INIT


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class TestRead:
    """Test read request/response orchestration.

    Read flow:
    1. Encode and send read telegram
    2. Wait for ACK (with one retry)
    3. Read response frame
    4. Decode and validate
    5. Send ACK
    6. Return payload

    Technique: Specification-based + Branch/Condition Coverage.
    """

    async def test_happy_path(self) -> None:
        """Full read cycle — ACK, valid response, ACK sent back.

        Technique: Specification-based — nominal flow.
        """
        address = 0x5525
        payload = b"\xef\x00"
        response = build_response(address, payload)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        result = await session.read(address, len(payload))

        assert result == payload
        # Last write should be ACK (confirming receipt)
        assert fake.written[-1] == ACK

    async def test_no_ack_first_time_ack_on_retry(self) -> None:
        """First read is not ACK, retry gets ACK — succeeds.

        Technique: Branch/Condition Coverage — retry path.
        """
        address = 0x0800
        payload = b"\x42"
        response = build_response(address, payload)

        fake = FakeSerial([b"\x00", ACK, response])
        session = P300Session(fake)

        result = await session.read(address, len(payload))

        assert result == payload

    async def test_no_ack_after_retry_raises(self) -> None:
        """No ACK on either attempt — DeviceError.

        Technique: Error Guessing — persistent NAK.
        """
        fake = FakeSerial([b"\x00", b"\x00"])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="no ACK after read request"):
            await session.read(0x0800, 2)

    async def test_error_response_raises(self) -> None:
        """Device returns P300Type.ERROR response — DeviceError.

        Technique: Equivalence Partitioning — error response class.
        """
        address = 0x0800
        payload = b"\x00\x00"
        error_response = build_response(address, payload, error=True)

        fake = FakeSerial([ACK, error_response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="error response from device"):
            await session.read(address, len(payload))

    async def test_correct_telegram_sent(self) -> None:
        """Verify the exact read request telegram bytes written to port.

        Technique: Specification-based — telegram encoding verification.
        """
        address = 0x5525
        length = 2
        expected_telegram = encode_read_request(address=address, data_length=length)
        response = build_response(address, b"\xef\x00")

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)
        await session.read(address, length)

        # First write is the read request telegram
        assert fake.written[0] == expected_telegram

    async def test_ack_sent_after_successful_response(self) -> None:
        """ACK is written back after receiving a valid response.

        Technique: Specification-based — protocol requirement.
        """
        address = 0x0800
        payload = b"\x42\x00"
        response = build_response(address, payload)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)
        await session.read(address, len(payload))

        # Writes: [telegram, ACK]
        assert len(fake.written) == 2
        assert fake.written[1] == ACK

    async def test_returns_correct_payload_bytes(self) -> None:
        """Returned bytes match the payload embedded in the response.

        Technique: Specification-based — data fidelity.
        """
        address = 0x0800
        payload = b"\x01\x02\x03\x04"
        response = build_response(address, payload)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        result = await session.read(address, len(payload))

        assert result == payload
        assert isinstance(result, bytes)

    async def test_telegram_error_propagates(self) -> None:
        """TelegramError from decode_telegram propagates to caller.

        Technique: Error Guessing — malformed response frame.
        """
        fake = FakeSerial([ACK, b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"])
        session = P300Session(fake)

        with pytest.raises(TelegramError):
            await session.read(0x0800, 2)


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


class TestWrite:
    """Test write request/response orchestration.

    Write flow mirrors read but sends a payload in the request and
    does not return data.

    Technique: Specification-based + Branch/Condition Coverage.
    """

    async def test_happy_path(self) -> None:
        """Full write cycle — ACK, valid response, ACK back.

        Technique: Specification-based — nominal flow.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(address, payload, mode=P300Mode.WRITE)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        await session.write(address, payload)  # Should not raise

        assert fake.written[-1] == ACK

    async def test_no_ack_after_retry_raises(self) -> None:
        """No ACK on either attempt — DeviceError.

        Technique: Error Guessing — persistent NAK.
        """
        fake = FakeSerial([b"\x00", b"\x00"])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="no ACK after write request"):
            await session.write(0x6300, b"\x2d")

    async def test_error_response_raises(self) -> None:
        """Device returns error response — DeviceError.

        Technique: Equivalence Partitioning — error response class.
        """
        address = 0x6300
        payload = b"\x2d"
        error_response = build_response(
            address, payload, error=True, mode=P300Mode.WRITE
        )

        fake = FakeSerial([ACK, error_response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="error response from device"):
            await session.write(address, payload)

    async def test_correct_telegram_sent(self) -> None:
        """Verify exact write request telegram bytes written to port.

        Technique: Specification-based — telegram encoding verification.
        """
        address = 0x6300
        payload = b"\x2d"
        expected_telegram = encode_write_request(address=address, payload=payload)
        response = build_response(address, payload, mode=P300Mode.WRITE)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)
        await session.write(address, payload)

        assert fake.written[0] == expected_telegram

    async def test_ack_sent_after_successful_write(self) -> None:
        """ACK written back after receiving valid write response.

        Technique: Specification-based — protocol requirement.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(address, payload, mode=P300Mode.WRITE)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)
        await session.write(address, payload)

        assert len(fake.written) == 2
        assert fake.written[1] == ACK

    async def test_no_ack_first_time_ack_on_retry(self) -> None:
        """First read is not ACK, retry succeeds — write completes.

        Technique: Branch/Condition Coverage — retry path.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(address, payload, mode=P300Mode.WRITE)

        fake = FakeSerial([b"\x00", ACK, response])
        session = P300Session(fake)

        await session.write(address, payload)  # Should not raise

        assert fake.written[-1] == ACK


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    """Test async context manager lifecycle.

    Technique: State Transition — session lifecycle.
    """

    async def test_aenter_performs_handshake(self) -> None:
        """__aenter__ runs the initialization handshake.

        Technique: Specification-based — entry triggers init.
        """
        fake = FakeSerial([NOT_INIT, ACK])

        async with P300Session(fake) as session:
            assert isinstance(session, P300Session)

        # SYNC was sent during handshake
        assert SYNC in fake.written

    async def test_aexit_closes_port(self) -> None:
        """__aexit__ calls port.close().

        Technique: Specification-based — resource cleanup.
        """
        fake = FakeSerial([ACK])

        async with P300Session(fake):
            assert not fake.closed

        assert fake.closed

    async def test_handshake_failure_closes_port(self) -> None:
        """If handshake fails, port is still closed.

        When __aenter__ raises DeviceError, __aexit__ is NOT called
        by the ``async with`` machinery. The session must close the
        port itself before re-raising.

        Technique: Error Guessing — cleanup on init failure.
        """
        fake = FakeSerial()  # No data → all reads timeout → exhausts retries
        session = P300Session(fake, max_init_retries=2)

        with pytest.raises(DeviceError, match="initialization failed"):
            async with session:
                pass  # Should never reach here

        assert fake.closed

    async def test_non_device_error_during_init_closes_port(self) -> None:
        """Non-DeviceError (e.g. OSError) during handshake still closes port.

        The transport widens its except clause to ``Exception`` so real
        serial layer errors don't leak the port handle.

        Technique: Error Guessing — underlying I/O failure during init.
        """

        class BrokenSerial(FakeSerial):
            async def read(self, n: int) -> bytes:
                raise OSError("serial port disconnected")

        fake = BrokenSerial()

        with pytest.raises(OSError, match="serial port disconnected"):
            async with P300Session(fake):
                pass

        assert fake.closed

    async def test_session_usable_after_enter(self) -> None:
        """Read and write work after successful __aenter__.

        Technique: Specification-based — functional session post-init.
        """
        address = 0x5525
        payload = b"\xef\x00"
        response = build_response(address, payload)

        fake = FakeSerial([ACK])  # Init: immediate ACK
        fake.push(ACK, response)  # Read: ACK + response

        async with P300Session(fake) as session:
            result = await session.read(address, len(payload))

        assert result == payload


# ---------------------------------------------------------------------------
# SerialPort protocol
# ---------------------------------------------------------------------------


class TestSerialPortProtocol:
    """Verify the SerialPort protocol definition and conformance.

    Technique: Specification-based — protocol structural typing.
    """

    def test_fake_serial_satisfies_protocol(self) -> None:
        """FakeSerial is a valid SerialPort (runtime_checkable).

        Technique: Specification-based — structural subtyping.
        """
        fake = FakeSerial()
        assert isinstance(fake, SerialPort)

    def test_protocol_has_required_methods(self) -> None:
        """SerialPort declares read, write, close.

        Technique: Specification-based — interface completeness.
        """
        # Protocol members are available via __protocol_attrs__
        # or by checking the protocol directly
        for method_name in ("read", "write", "close"):
            assert hasattr(SerialPort, method_name)


# ---------------------------------------------------------------------------
# Response echo validation
# ---------------------------------------------------------------------------


class TestReadEchoValidation:
    """Verify that read() validates response mode, address, and data_length.

    The P300 session must check that the response frame echoes the
    request parameters, catching stale or out-of-order responses.

    Technique: Defensive Programming — echo validation.
    """

    async def test_mismatched_address_raises(self) -> None:
        """Response with wrong address triggers DeviceError.

        Technique: Error Guessing — stale response from previous request.
        """
        address = 0x0800
        payload = b"\x42\x00"
        wrong_address = 0x5525
        response = build_response(address, payload, override_address=wrong_address)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*address"):
            await session.read(address, len(payload))

    async def test_mismatched_mode_raises(self) -> None:
        """Response with WRITE mode for a READ request triggers DeviceError.

        Technique: Error Guessing — protocol confusion.
        """
        address = 0x0800
        payload = b"\x42\x00"
        response = build_response(address, payload, override_mode=P300Mode.WRITE)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*mode"):
            await session.read(address, len(payload))

    async def test_mismatched_data_length_raises(self) -> None:
        """Response with wrong data_length field triggers DeviceError.

        Technique: Error Guessing — corrupted length field.
        """
        address = 0x0800
        payload = b"\x42\x00"
        response = build_response(address, payload, override_data_length=4)

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*data_length"):
            await session.read(address, len(payload))


class TestWriteEchoValidation:
    """Verify that write() validates response mode, address, and data_length.

    Technique: Defensive Programming — echo validation for writes.
    """

    async def test_mismatched_address_raises(self) -> None:
        """Write response with wrong address triggers DeviceError.

        Technique: Error Guessing — stale response.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(
            address,
            payload,
            mode=P300Mode.WRITE,
            override_address=0x0800,
        )

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*address"):
            await session.write(address, payload)

    async def test_mismatched_mode_raises(self) -> None:
        """Write response with READ mode triggers DeviceError.

        Technique: Error Guessing — mode confusion.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(
            address,
            payload,
            mode=P300Mode.WRITE,
            override_mode=P300Mode.READ,
        )

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*mode"):
            await session.write(address, payload)

    async def test_mismatched_data_length_raises(self) -> None:
        """Write response with wrong data_length triggers DeviceError.

        Technique: Error Guessing — corrupted response.
        """
        address = 0x6300
        payload = b"\x2d"
        response = build_response(
            address,
            payload,
            mode=P300Mode.WRITE,
            override_data_length=4,
        )

        fake = FakeSerial([ACK, response])
        session = P300Session(fake)

        with pytest.raises(DeviceError, match="echo mismatch.*data_length"):
            await session.write(address, payload)
