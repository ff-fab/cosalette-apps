"""Unit tests for airthings2mqtt ports — AirthingsReading dataclass.

Test Techniques Used:
- Specification-based: Verify dataclass fields and immutability
- Error Guessing: Frozen dataclass mutation attempt
"""

from __future__ import annotations

import pytest

from airthings2mqtt.ports import AirthingsReading


@pytest.mark.unit
class TestAirthingsReading:
    """Verify AirthingsReading dataclass behavior."""

    def test_creation_with_values(self) -> None:
        """AirthingsReading stores all four sensor values."""
        reading = AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
        )
        assert reading.temperature == 21.5
        assert reading.humidity == 45.0
        assert reading.radon_24h_avg == 80
        assert reading.radon_long_term_avg == 65

    def test_frozen_immutability(self) -> None:
        """AirthingsReading is frozen — mutation raises FrozenInstanceError.

        Technique: Error Guessing — anticipating specific failure mode.
        """
        reading = AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
        )
        with pytest.raises(AttributeError):
            reading.temperature = 99.0  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two readings with identical values are equal."""
        a = AirthingsReading(
            temperature=21.5, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )
        b = AirthingsReading(
            temperature=21.5, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )
        assert a == b

    def test_inequality(self) -> None:
        """Readings with different values are not equal."""
        a = AirthingsReading(
            temperature=21.5, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )
        b = AirthingsReading(
            temperature=22.0, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )
        assert a != b
