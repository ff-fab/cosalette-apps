"""UDP Wake-on-LAN adapter implementing WolPort.

Sends WoL magic packets via UDP broadcast. The magic packet format
is 6 bytes of 0xFF followed by 16 repetitions of the target MAC
address (102 bytes total), sent to the broadcast address on port 9.

No external dependencies — uses stdlib socket module.
"""

from __future__ import annotations

import asyncio
import logging
import re
import socket

logger = logging.getLogger(__name__)

_MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$|^[0-9A-Fa-f]{12}$")
_WOL_PORT = 9


def _parse_mac(mac: str) -> bytes:
    """Parse a MAC address string into 6 bytes.

    Accepts formats: AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF.

    Args:
        mac: MAC address string.

    Returns:
        6-byte MAC address.

    Raises:
        ValueError: If the MAC format is invalid.
    """
    if not _MAC_PATTERN.match(mac):
        msg = f"Invalid MAC address: {mac!r}"
        raise ValueError(msg)
    hex_str = mac.replace(":", "").replace("-", "")
    return bytes.fromhex(hex_str)


def _build_magic_packet(mac_bytes: bytes) -> bytes:
    """Build a WoL magic packet from parsed MAC bytes.

    Format: 6 bytes of 0xFF + 16 repetitions of the 6-byte MAC = 102 bytes.

    Args:
        mac_bytes: 6-byte MAC address.

    Returns:
        102-byte magic packet.
    """
    return b"\xff" * 6 + mac_bytes * 16


class UdpWol:
    """Wake-on-LAN adapter using UDP broadcast.

    Sends magic packets via a UDP socket to wake a sleeping device.
    """

    async def wake(self, mac: str, broadcast: str) -> None:
        """Send a Wake-on-LAN magic packet.

        Args:
            mac: MAC address of target device.
            broadcast: Broadcast address for the UDP packet.

        Raises:
            ValueError: If the MAC address format is invalid.
        """
        mac_bytes = _parse_mac(mac)
        packet = _build_magic_packet(mac_bytes)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_packet, packet, broadcast)
        logger.info("WoL packet sent to %s via %s", mac, broadcast)


def _send_packet(packet: bytes, broadcast: str) -> None:
    """Send a magic packet via UDP broadcast socket.

    Args:
        packet: The 102-byte magic packet.
        broadcast: Broadcast address.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, _WOL_PORT))
