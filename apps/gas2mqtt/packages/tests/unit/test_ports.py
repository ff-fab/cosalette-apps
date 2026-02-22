"""Unit tests for gas2mqtt ports — MagneticReading dataclass.

Test Techniques Used:
- Specification-based: Verify dataclass fields and immutability
- Error Guessing: Frozen dataclass mutation attempt
"""

from __future__ import annotations

import pytest

from gas2mqtt.ports import MagneticReading


@pytest.mark.unit
class TestMagneticReading:
    """Verify MagneticReading dataclass behavior."""

    def test_creation_with_values(self) -> None:
        """MagneticReading stores all four axis values."""
        reading = MagneticReading(bx=100, by=200, bz=-5000, temperature_raw=2500)
        assert reading.bx == 100
        assert reading.by == 200
        assert reading.bz == -5000
        assert reading.temperature_raw == 2500

    def test_frozen_immutability(self) -> None:
        """MagneticReading is frozen — mutation raises FrozenInstanceError.

        Technique: Error Guessing — anticipating specific failure mode.
        """
        reading = MagneticReading(bx=0, by=0, bz=0, temperature_raw=0)
        with pytest.raises(AttributeError):
            reading.bx = 42  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two readings with identical values are equal."""
        a = MagneticReading(bx=1, by=2, bz=3, temperature_raw=4)
        b = MagneticReading(bx=1, by=2, bz=3, temperature_raw=4)
        assert a == b

    def test_inequality(self) -> None:
        """Readings with different values are not equal."""
        a = MagneticReading(bx=1, by=2, bz=3, temperature_raw=4)
        b = MagneticReading(bx=1, by=2, bz=99, temperature_raw=4)
        assert a != b
