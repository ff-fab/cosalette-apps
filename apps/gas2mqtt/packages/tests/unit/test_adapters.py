"""Unit tests for gas2mqtt adapters — FakeMagnetometer.

Test Techniques Used:
- Specification-based: Verify protocol compliance and default behavior
- State Transition: initialize → read → close lifecycle
"""

from __future__ import annotations

import pytest

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.ports import MagneticReading


@pytest.mark.unit
class TestFakeMagnetometer:
    """Verify FakeMagnetometer satisfies MagnetometerPort protocol."""

    def test_default_values_are_zero(self) -> None:
        """All readings default to 0."""
        mag = FakeMagnetometer()
        reading = mag.read()
        assert reading == MagneticReading(bx=0, by=0, bz=0, temperature_raw=0)

    def test_configurable_values(self) -> None:
        """Setting bz affects the next read."""
        mag = FakeMagnetometer()
        mag.bz = -5000
        mag.temperature_raw = 2500
        reading = mag.read()
        assert reading.bz == -5000
        assert reading.temperature_raw == 2500

    def test_lifecycle_initialize(self) -> None:
        """initialize() marks the adapter as initialized."""
        mag = FakeMagnetometer()
        assert mag.initialized is False
        mag.initialize()
        assert mag.initialized is True

    def test_lifecycle_close(self) -> None:
        """close() marks the adapter as closed."""
        mag = FakeMagnetometer()
        assert mag.closed is False
        mag.close()
        assert mag.closed is True

    def test_full_lifecycle(self) -> None:
        """Full lifecycle: init → read → close.

        Technique: State Transition — verify expected state changes.
        """
        mag = FakeMagnetometer()
        mag.initialize()
        assert mag.initialized is True

        mag.bz = -3000
        reading = mag.read()
        assert reading.bz == -3000

        mag.close()
        assert mag.closed is True

    def test_returns_magnetic_reading_type(self) -> None:
        """read() returns a proper MagneticReading instance."""
        mag = FakeMagnetometer()
        reading = mag.read()
        assert isinstance(reading, MagneticReading)
