"""Unit tests for airthings2mqtt ports — AirthingsReading dataclass.

Test Techniques Used:
- Specification-based: Verify dataclass fields and immutability
- Error Guessing: Frozen dataclass mutation attempt
- Equivalence Partitioning: Value fields vs. read time in equality
"""

from __future__ import annotations

from datetime import UTC, datetime

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

    def test_radon_fields_accept_none(self) -> None:
        """Both radon fields accept None (Wave 2 out-of-range guard).

        Technique: Specification-based — the Wave 2 decoder maps an implausible
        radon reading to None; the state_model must permit it.
        """
        reading = AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=None,
            radon_long_term_avg=None,
        )
        assert reading.radon_24h_avg is None
        assert reading.radon_long_term_avg is None

    def test_read_health_fields_default(self) -> None:
        """last_read defaults to an aware UTC now; rssi defaults to None.

        Technique: Specification-based — a reading built without an
        advertisement or explicit stamp is still publishable.
        """
        before = datetime.now(UTC)
        reading = AirthingsReading(
            temperature=21.5, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )
        assert before <= reading.last_read <= datetime.now(UTC)
        assert reading.rssi is None

    def test_last_read_excluded_from_equality(self) -> None:
        """Readings with the same values but different read times are equal.

        Technique: Equivalence Partitioning — read time is not part of a
        reading's value identity; rssi is.
        """
        values = {
            "temperature": 21.5,
            "humidity": 45.0,
            "radon_24h_avg": 80,
            "radon_long_term_avg": 65,
        }
        a = AirthingsReading(**values, last_read=datetime(2026, 1, 1, tzinfo=UTC))
        b = AirthingsReading(**values, last_read=datetime(2026, 1, 2, tzinfo=UTC))
        assert a == b
        assert a != AirthingsReading(**values, rssi=-70)
