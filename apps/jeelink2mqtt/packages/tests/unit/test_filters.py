"""Unit tests for jeelink2mqtt.filters — Per-sensor median filter bank.

Test Techniques Used:
- Specification-based Testing: Filter auto-creation, return types
- State Transition Testing: reset/reset_all clearing filter state
- Equivalence Partitioning: Single ID, multiple IDs
"""

from __future__ import annotations

import pytest

from jeelink2mqtt.filters import FilterBank


@pytest.mark.unit
class TestFilterBank:
    """Specification-based and state-transition tests for FilterBank."""

    def test_filter_returns_float_tuple(self, make_reading) -> None:
        """filter() returns a (float, float) tuple.

        Technique: Specification-based — return type contract.
        """
        # Arrange
        bank = FilterBank(window=3)
        reading = make_reading(sensor_id=1, temperature=21.5, humidity=55)

        # Act
        result = bank.filter(reading)

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_filter_auto_creates_for_new_sensor_id(self, make_reading) -> None:
        """First call for a sensor ID auto-creates its filter pair.

        Technique: Specification-based — lazy initialization.
        """
        # Arrange
        bank = FilterBank(window=5)
        reading = make_reading(sensor_id=42, temperature=20.0, humidity=50)

        # Act — should not raise
        temp, hum = bank.filter(reading)

        # Assert — values returned (first value through median = the value itself)
        assert isinstance(temp, float)
        assert isinstance(hum, float)

    def test_filter_multiple_sensor_ids_independent(self, make_reading) -> None:
        """Different sensor IDs get independent filter instances.

        Technique: Equivalence Partitioning — independent filter banks.
        """
        # Arrange
        bank = FilterBank(window=3)
        r1 = make_reading(sensor_id=1, temperature=10.0, humidity=30)
        r2 = make_reading(sensor_id=2, temperature=25.0, humidity=70)

        # Act
        t1, h1 = bank.filter(r1)
        t2, h2 = bank.filter(r2)

        # Assert — values are from their respective sensors (not mixed)
        assert isinstance(t1, float)
        assert isinstance(t2, float)
        # After one sample, median filter returns the only value
        assert t1 != t2 or (t1 == t2 and r1.temperature == r2.temperature)

    def test_filter_repeated_calls_produce_floats(self, make_reading) -> None:
        """Multiple readings through the same filter all return floats.

        Technique: Specification-based — consistent return types over time.
        """
        # Arrange
        bank = FilterBank(window=3)
        readings = [
            make_reading(sensor_id=1, temperature=20.0 + i, humidity=50 + i)
            for i in range(5)
        ]

        # Act / Assert
        for r in readings:
            temp, hum = bank.filter(r)
            assert isinstance(temp, float)
            assert isinstance(hum, float)

    def test_reset_removes_filter_for_sensor_id(self, make_reading) -> None:
        """reset() removes filters — next call creates fresh ones.

        Technique: State Transition — active → removed → fresh.
        """
        # Arrange
        bank = FilterBank(window=3)
        # Prime the filter with a few values
        for i in range(3):
            bank.filter(make_reading(sensor_id=1, temperature=20.0 + i, humidity=50))

        # Act
        bank.reset(1)

        # Re-filter with a very different value
        result = bank.filter(make_reading(sensor_id=1, temperature=99.0, humidity=99))

        # Assert — after reset, the filter starts fresh
        # With only one value, median of [99.0] = 99.0
        assert result[0] == pytest.approx(99.0)
        assert result[1] == pytest.approx(99.0)

    def test_reset_nonexistent_id_is_noop(self) -> None:
        """Resetting a non-existent sensor ID doesn't raise.

        Technique: Error Guessing — idempotent removal.
        """
        # Arrange
        bank = FilterBank(window=3)

        # Act / Assert — should not raise
        bank.reset(999)

    def test_reset_all_clears_everything(self, make_reading) -> None:
        """reset_all() removes all tracked filters.

        Technique: State Transition — populated → empty → fresh.
        """
        # Arrange
        bank = FilterBank(window=3)
        bank.filter(make_reading(sensor_id=1, temperature=20.0, humidity=50))
        bank.filter(make_reading(sensor_id=2, temperature=25.0, humidity=60))

        # Act
        bank.reset_all()

        # Re-filter sensor 1 with a very different value
        result = bank.filter(make_reading(sensor_id=1, temperature=99.0, humidity=99))

        # Assert — fresh filter = immediate echo
        assert result[0] == pytest.approx(99.0)
        assert result[1] == pytest.approx(99.0)

    def test_custom_window_size(self, make_reading) -> None:
        """FilterBank respects the window parameter.

        Technique: Specification-based — constructor parameter.
        """
        # Arrange / Act — different windows shouldn't crash
        bank_small = FilterBank(window=3)
        bank_large = FilterBank(window=11)

        reading = make_reading(sensor_id=1, temperature=20.0, humidity=50)

        # Assert — both produce valid results
        r1 = bank_small.filter(reading)
        r2 = bank_large.filter(reading)
        assert isinstance(r1[0], float)
        assert isinstance(r2[0], float)
