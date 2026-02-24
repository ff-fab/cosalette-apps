"""Unit tests for magnetometer telemetry — raw sensor output.

Tests the debug magnetometer pipeline: raw reading → dict output.
The handler is inline in main.py, so we test the same logic directly.

Test Techniques Used:
- Specification-based: Raw sensor values in output
"""

from __future__ import annotations

import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer


@pytest.mark.unit
class TestMagnetometerHandler:
    """Verify debug magnetometer output returns raw sensor values."""

    def test_returns_all_axes(self) -> None:
        """Handler returns bx, by, bz from the magnetometer.

        Technique: Specification-based — output contract.
        """
        # Arrange
        mag = FakeMagnetometer()
        mag.bx = 100
        mag.by = -200
        mag.bz = -5000

        # Act — simulate the inline handler logic
        reading = mag.read()
        result = {"bx": reading.bx, "by": reading.by, "bz": reading.bz}

        # Assert
        assert result == {"bx": 100, "by": -200, "bz": -5000}
