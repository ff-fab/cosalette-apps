"""Unit tests for gas2mqtt/devices/magnetometer.py — Debug magnetometer device.

Test Techniques Used:
- Specification-based: Raw sensor values in output
- Equivalence Partitioning: Various magnetic field values
- State Transition: Values update between reads
- Error Guessing: Temperature data leakage
"""

from __future__ import annotations

import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.magnetometer import make_magnetometer_handler


@pytest.mark.unit
class TestMagnetometerHandler:
    """Verify debug magnetometer handler returns raw sensor values."""

    async def test_returns_all_axes(self) -> None:
        """Handler returns bx, by, bz from the magnetometer.

        Technique: Specification-based — output contract.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.bx = 100
        mag.by = -200
        mag.bz = -5000
        handler = make_magnetometer_handler(mag)

        # Act
        result = await handler()

        # Assert
        assert result == {"bx": 100, "by": -200, "bz": -5000}

    async def test_returns_zeros_by_default(self) -> None:
        """Fresh FakeMagnetometer returns all zeros.

        Technique: Specification-based — default fake values.
        """
        # Arrange
        mag = FakeMagnetometer()
        handler = make_magnetometer_handler(mag)

        # Act
        result = await handler()

        # Assert
        assert result == {"bx": 0, "by": 0, "bz": 0}

    async def test_reflects_updated_values(self) -> None:
        """Changing fake values between calls produces updated output.

        Technique: State Transition — values update between reads.
        """
        # Arrange
        mag = FakeMagnetometer()
        handler = make_magnetometer_handler(mag)

        # Act 1 — initial read
        result1 = await handler()

        # Update values
        mag.bx = 42
        mag.by = 43
        mag.bz = 44

        # Act 2 — updated read
        result2 = await handler()

        # Assert
        assert result1 == {"bx": 0, "by": 0, "bz": 0}
        assert result2 == {"bx": 42, "by": 43, "bz": 44}

    async def test_does_not_include_temperature(self) -> None:
        """Debug output excludes temperature (separate device handles that).

        Technique: Error Guessing — ensuring no data leakage.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.temperature_raw = 9999
        handler = make_magnetometer_handler(mag)

        # Act
        result = await handler()

        # Assert
        assert "temperature" not in result
        assert "temperature_raw" not in result
