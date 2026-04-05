"""Unit tests for adapters/wol_adapter.py — UdpWol Wake-on-LAN adapter.

Test Techniques Used:
- Equivalence Partitioning: Valid MAC formats (colon, dash, bare) vs invalid
- Boundary Value Analysis: Magic packet byte structure (102 bytes)
- Error Guessing: Invalid MAC strings, empty input
- Specification-based Testing: WolPort protocol compliance
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from wallpanel_control.adapters.wol_adapter import (
    UdpWol,
    _build_magic_packet,
    _parse_mac,
)
from wallpanel_control.ports import WolPort


# =============================================================================
# Protocol compliance
# =============================================================================


@pytest.mark.unit
class TestUdpWolProtocol:
    """Verify UdpWol satisfies WolPort protocol."""

    def test_satisfies_wol_port(self) -> None:
        """UdpWol is a structural subtype of WolPort."""
        # Arrange
        wol = UdpWol()

        # Act / Assert
        assert isinstance(wol, WolPort)


# =============================================================================
# MAC parsing
# =============================================================================


@pytest.mark.unit
class TestParseMac:
    """Verify MAC address parsing from multiple formats.

    Technique: Equivalence Partitioning — three valid formats, several invalid.
    """

    @pytest.mark.parametrize(
        ("mac_str", "expected_hex"),
        [
            ("AA:BB:CC:DD:EE:FF", "aabbccddeeff"),
            ("aa:bb:cc:dd:ee:ff", "aabbccddeeff"),
            ("AA-BB-CC-DD-EE-FF", "aabbccddeeff"),
            ("AABBCCDDEEFF", "aabbccddeeff"),
            ("aabbccddeeff", "aabbccddeeff"),
            ("00:11:22:33:44:55", "001122334455"),
        ],
        ids=[
            "colon-upper",
            "colon-lower",
            "dash-upper",
            "bare-upper",
            "bare-lower",
            "colon-with-zeros",
        ],
    )
    def test_parse_valid_mac(self, mac_str: str, expected_hex: str) -> None:
        """Valid MAC formats are parsed to correct bytes."""
        # Act
        result = _parse_mac(mac_str)

        # Assert
        assert result == bytes.fromhex(expected_hex)

    @pytest.mark.parametrize(
        "invalid_mac",
        [
            "",
            "not-a-mac",
            "AA:BB:CC:DD:EE",
            "AA:BB:CC:DD:EE:FF:00",
            "GG:HH:II:JJ:KK:LL",
            "AA:BB:CC:DD:EE:F",
            "AABBCCDDEEF",
            "AABBCCDDEEFFG",
        ],
        ids=[
            "empty",
            "garbage",
            "too-short-colon",
            "too-long-colon",
            "invalid-hex-chars",
            "incomplete-octet",
            "bare-too-short",
            "bare-invalid-char",
        ],
    )
    def test_parse_invalid_mac_raises(self, invalid_mac: str) -> None:
        """Invalid MAC formats raise ValueError."""
        # Act / Assert
        with pytest.raises(ValueError, match="Invalid MAC address"):
            _parse_mac(invalid_mac)


# =============================================================================
# Magic packet construction
# =============================================================================


@pytest.mark.unit
class TestBuildMagicPacket:
    """Verify magic packet byte structure.

    Technique: Boundary Value Analysis — exact packet size and content.
    """

    def test_packet_length(self) -> None:
        """Magic packet is exactly 102 bytes."""
        # Arrange
        mac_bytes = bytes.fromhex("aabbccddeeff")

        # Act
        packet = _build_magic_packet(mac_bytes)

        # Assert
        assert len(packet) == 102

    def test_packet_starts_with_six_ff_bytes(self) -> None:
        """First 6 bytes are all 0xFF."""
        # Arrange
        mac_bytes = bytes.fromhex("aabbccddeeff")

        # Act
        packet = _build_magic_packet(mac_bytes)

        # Assert
        assert packet[:6] == b"\xff" * 6

    def test_packet_contains_16_mac_repetitions(self) -> None:
        """Bytes 6-102 contain 16 repetitions of the MAC address."""
        # Arrange
        mac_bytes = bytes.fromhex("aabbccddeeff")

        # Act
        packet = _build_magic_packet(mac_bytes)

        # Assert
        mac_section = packet[6:]
        assert len(mac_section) == 96
        for i in range(16):
            assert mac_section[i * 6 : (i + 1) * 6] == mac_bytes


# =============================================================================
# UdpWol.wake() integration with mocked socket
# =============================================================================


@pytest.mark.unit
class TestUdpWolWake:
    """Verify wake() sends correct packet via UDP broadcast.

    Technique: Specification-based — mock socket to verify sent bytes.
    """

    async def test_wake_sends_magic_packet(self) -> None:
        """wake() sends a 102-byte magic packet to broadcast:9."""
        # Arrange
        wol = UdpWol()
        mock_socket = MagicMock()
        mac = "AA:BB:CC:DD:EE:FF"
        broadcast = "192.168.1.255"

        with patch(
            "wallpanel_control.adapters.wol_adapter.socket.socket"
        ) as mock_socket_cls:
            mock_socket_cls.return_value.__enter__ = MagicMock(return_value=mock_socket)
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)

            # Act
            await wol.wake(mac, broadcast)

        # Assert
        mock_socket.sendto.assert_called_once()
        sent_packet, (sent_addr, sent_port) = mock_socket.sendto.call_args[0]
        assert len(sent_packet) == 102
        assert sent_packet[:6] == b"\xff" * 6
        assert sent_addr == broadcast
        assert sent_port == 9

    async def test_wake_invalid_mac_raises(self) -> None:
        """wake() raises ValueError for invalid MAC before sending."""
        # Arrange
        wol = UdpWol()

        # Act / Assert
        with pytest.raises(ValueError, match="Invalid MAC address"):
            await wol.wake("not-a-mac", "192.168.1.255")
