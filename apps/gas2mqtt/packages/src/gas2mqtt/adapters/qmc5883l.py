"""QMC5883L magnetometer adapter — production I2C implementation.

Reads from the QMC5883L 3-axis digital magnetometer via the I2C bus
using smbus2. The QMC5883L is a multi-chip module containing a 3-axis
magnetic sensor with on-die temperature compensation.

I2C address: 0x0D (default for QMC5883L)
Data register: 0x00 (9 bytes)
  Bytes 0-1: X axis (little-endian signed 16-bit)
  Bytes 2-3: Y axis (little-endian signed 16-bit)
  Bytes 4-5: Z axis (little-endian signed 16-bit)
  Byte 6: Status register
  Bytes 7-8: Temperature (little-endian signed 16-bit)

Configuration:
  Register 0x09: Control Register 1
  Register 0x0B: SET/RESET Period Register

Note: Despite some legacy references to "HMC5883", the actual hardware
is a QMC5883L — a lower-cost successor with a different register map.
"""

from __future__ import annotations

import logging

import smbus2

from gas2mqtt.ports import MagneticReading

logger = logging.getLogger(__name__)


def _to_signed_16_le(lsb: int, msb: int) -> int:
    """Convert two bytes (little-endian) to a signed 16-bit integer.

    The QMC5883L outputs data in little-endian byte order.

    Args:
        lsb: Least significant byte (lower address).
        msb: Most significant byte (higher address).

    Returns:
        Signed 16-bit integer value (-32768 to 32767).
    """
    value = (msb << 8) | lsb
    if value >= 0x8000:
        value -= 0x10000
    return value


class Qmc5883lAdapter:
    """Production adapter for the QMC5883L magnetometer over I2C.

    Implements MagnetometerPort protocol. Reads magnetic field (X, Y, Z)
    and temperature from the QMC5883L via smbus2.

    The QMC5883L data output register layout (starting at 0x00):
        Bytes 0-1: X axis (little-endian signed 16)
        Bytes 2-3: Y axis (little-endian signed 16)
        Bytes 4-5: Z axis (little-endian signed 16)
        Byte 6: Status register
        Bytes 7-8: Temperature (little-endian signed 16)
    """

    def __init__(self, bus_number: int = 1, address: int = 0x0D) -> None:
        self._bus_number = bus_number
        self._address = address
        self._bus: smbus2.SMBus | None = None

    def initialize(self) -> None:
        """Open I2C bus and configure the QMC5883L.

        Control Register 1 (0x09): 0b11010001
            - Continuous measurement mode (bits 0-1: 01)
            - Output data rate: 10 Hz (bits 2-3: 00)
            - Full scale range: 8 Gauss (bits 4-5: 01)
            - Over sample ratio: 64 (bits 6-7: 11)

        SET/RESET Period Register (0x0B): 0b00000001
            - Recommended value per datasheet.
        """
        self._bus = smbus2.SMBus(self._bus_number)
        self._bus.write_byte_data(self._address, 0x09, 0b11010001)
        self._bus.write_byte_data(self._address, 0x0B, 0b00000001)
        logger.info(
            "QMC5883L initialized on bus %d at address 0x%02X",
            self._bus_number,
            self._address,
        )

    def read(self) -> MagneticReading:
        """Read magnetic field (X, Y, Z) and temperature from the QMC5883L.

        Reads 9 bytes from register 0x00: X, Y, Z axes (little-endian)
        plus status byte and temperature (little-endian).

        Returns:
            MagneticReading with bx, by, bz, and temperature_raw.

        Raises:
            IOError: If I2C communication fails.
            RuntimeError: If the bus has not been initialized.
        """
        if self._bus is None:
            msg = "QMC5883L not initialized — call initialize() first"
            raise RuntimeError(msg)

        # Read 9 bytes starting at register 0x00
        data = self._bus.read_i2c_block_data(self._address, 0x00, 9)

        bx = _to_signed_16_le(data[0], data[1])
        by = _to_signed_16_le(data[2], data[3])
        bz = _to_signed_16_le(data[4], data[5])
        # Byte 6 is status — skip
        temperature_raw = _to_signed_16_le(data[7], data[8])

        return MagneticReading(bx=bx, by=by, bz=bz, temperature_raw=temperature_raw)

    def close(self) -> None:
        """Close the I2C bus connection."""
        if self._bus is not None:
            self._bus.close()
            self._bus = None
            logger.info("QMC5883L I2C bus closed")
