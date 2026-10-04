"""Unit tests for lifecycle.py — radon measurement lifecycle across a reset.

Test Techniques Used:
- State Transition Testing: ok -> warming_up -> provisional -> ok across a reset
- Boundary Value Analysis: LTA drop ratio, minimum previous LTA, settle period edge
- Decision Table: placeholder / collapse / settle conditions -> measurement_state
- Round-trip Testing: ResetState survives the device store's JSON form
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from airthings2mqtt.lifecycle import ResetState, track
from airthings2mqtt.ports import AirthingsReading

T0 = datetime(2026, 10, 2, 6, 3, 7, tzinfo=UTC)
SETTLE = timedelta(days=30)


def _reading(r24: int | None, lta: int | None, at: datetime = T0) -> AirthingsReading:
    return AirthingsReading(
        temperature=31.0,
        humidity=43.5,
        radon_24h_avg=r24,
        radon_long_term_avg=lta,
        last_read=at,
    )


@pytest.mark.unit
class TestTrackReset:
    """The incident sequence from the proposal (acceptance criteria 1-5)."""

    def test_double_zero_after_reading_is_reset_and_withheld(self) -> None:
        """0/0 after LTA 113: radon null, warming_up, reset recorded.

        Technique: State Transition — ok -> warming_up.
        """
        # Act
        reading, state, reset = track(_reading(0, 0), ResetState(last_lta=113), SETTLE)

        # Assert
        assert reset is True
        assert reading.radon_24h_avg is None
        assert reading.radon_long_term_avg is None
        assert reading.measurement_state == "warming_up"
        assert reading.sensor_reset_at == T0
        assert state == ResetState(
            last_lta=0, reset_at=T0, lta_before_reset=113, reset_count=1
        )

    def test_repeated_double_zero_is_not_a_second_reset(self) -> None:
        """Further 0/0 reads stay warming_up without a new reset.

        Technique: State Transition — warming_up -> warming_up.
        """
        # Arrange
        _, state, _ = track(_reading(0, 0), ResetState(last_lta=113), SETTLE)

        # Act
        reading, after, reset = track(
            _reading(0, 0, T0 + timedelta(hours=1)), state, SETTLE
        )

        # Assert
        assert reset is False
        assert after == state
        assert reading.measurement_state == "warming_up"

    def test_first_values_after_reset_are_provisional(self) -> None:
        """The first non-zero 24 h average is published, marked provisional.

        Technique: State Transition — warming_up -> provisional.
        """
        # Arrange
        _, state, _ = track(_reading(0, 0), ResetState(last_lta=113), SETTLE)

        # Act
        reading, after, reset = track(
            _reading(95, 4, T0 + timedelta(days=1)), state, SETTLE
        )

        # Assert
        assert reset is False
        assert (reading.radon_24h_avg, reading.radon_long_term_avg) == (95, 4)
        assert reading.measurement_state == "provisional"
        assert after.last_lta == 4

    @pytest.mark.parametrize(
        ("elapsed", "expected"),
        [
            (SETTLE - timedelta(seconds=1), "provisional"),
            (SETTLE, "ok"),
        ],
    )
    def test_long_term_average_settles_after_settle_period(
        self, elapsed: timedelta, expected: str
    ) -> None:
        """The provisional phase ends exactly lta_settle_days after the reset.

        Technique: Boundary Value Analysis — settle period edge.
        """
        # Arrange
        state = ResetState(last_lta=80, reset_at=T0, lta_before_reset=113)

        # Act
        reading, _, _ = track(_reading(90, 85, T0 + elapsed), state, SETTLE)

        # Assert
        assert reading.measurement_state == expected
        assert reading.sensor_reset_at == T0

    @pytest.mark.parametrize(
        ("previous", "current", "reset"),
        [
            (113, 5, True),  # proposal criterion 5
            (100, 24, True),  # just below 25 %
            (100, 25, False),  # exactly 25 %
            (19, 0, False),  # previous LTA too small to judge; 24 h stays > 0
            (20, 4, True),  # smallest previous LTA that counts
        ],
    )
    def test_collapsed_long_term_average_is_a_reset(
        self, previous: int, current: int, reset: bool
    ) -> None:
        """A long-term average falling below 25 % of a previous >= 20 is a reset.

        Technique: Boundary Value Analysis — drop ratio and minimum LTA.
        """
        # Act
        reading, state, detected = track(
            _reading(30, current), ResetState(last_lta=previous), SETTLE
        )

        # Assert
        assert detected is reset
        assert reading.radon_long_term_avg == current
        assert reading.measurement_state == ("provisional" if reset else "ok")
        assert state.lta_before_reset == (previous if reset else None)


@pytest.mark.unit
class TestTrackSteadyState:
    """Readings without a reset."""

    def test_normal_reading_is_ok_and_unchanged(self) -> None:
        """A reading with no reset history publishes as-is with state ok.

        Technique: Equivalence Partitioning — the ordinary case.
        """
        # Arrange
        raw = _reading(127, 113)

        # Act
        reading, state, reset = track(raw, ResetState(), SETTLE)

        # Assert
        assert reset is False
        assert reading == raw
        assert reading.measurement_state == "ok"
        assert reading.sensor_reset_at is None
        assert state == ResetState(last_lta=113)

    def test_first_ever_read_of_a_warming_sensor_records_a_reset(self) -> None:
        """A 0/0 read with an empty store is a sensor that just powered up.

        Technique: Error Guessing — fresh store, sensor fresh from a battery change.
        """
        # Act
        reading, state, reset = track(_reading(0, 0), ResetState(), SETTLE)

        # Assert
        assert reset is True
        assert reading.measurement_state == "warming_up"
        assert state.lta_before_reset is None
        assert state.reset_count == 1

    def test_out_of_range_frame_keeps_previous_long_term_average(self) -> None:
        """A dropped (None) LTA neither resets nor overwrites the history.

        Technique: Error Guessing — garbled frame between good reads.
        """
        # Act
        _, state, reset = track(_reading(None, None), ResetState(last_lta=113), SETTLE)

        # Assert
        assert reset is False
        assert state.last_lta == 113

    def test_zero_settle_period_skips_provisional(self) -> None:
        """lta_settle_days=0 goes straight from warming_up to ok.

        Technique: Boundary Value Analysis — settle period of zero.
        """
        # Arrange
        state = ResetState(last_lta=0, reset_at=T0, reset_count=1)

        # Act
        reading, _, _ = track(_reading(95, 4, T0), state, timedelta(0))

        # Assert
        assert reading.measurement_state == "ok"


@pytest.mark.unit
class TestResetStateRoundTrip:
    """ResetState survives the JSON device store (criterion 6)."""

    def test_round_trip_through_json(self) -> None:
        """to_dict -> JSON -> from_dict restores an equal state.

        Technique: Round-trip Testing.
        """
        # Arrange
        state = ResetState(last_lta=0, reset_at=T0, lta_before_reset=113, reset_count=2)

        # Act
        restored = ResetState.from_dict(json.loads(json.dumps(state.to_dict())))

        # Assert
        assert restored == state

    @pytest.mark.parametrize("stored", [None, {}, "garbage"])
    def test_missing_or_corrupt_entry_is_default_state(self, stored: object) -> None:
        """A store without usable tracker data yields the default state.

        Technique: Equivalence Partitioning — absent, empty and wrong-type input.
        """
        assert ResetState.from_dict(stored) == ResetState()

    @pytest.mark.parametrize(
        "stored",
        [
            {"reset_at": "not-a-timestamp"},
            {"reset_at": "2026-10-02T06:03:07"},
            {"reset_at": 123},
            {"last_lta": "113"},
            {"last_lta": True},
            {"lta_before_reset": "113"},
            {"lta_before_reset": False},
            {"reset_count": "2"},
            {"reset_count": True},
            {"reset_count": -1},
        ],
    )
    def test_malformed_fields_are_default_state(self, stored: object) -> None:
        """Malformed persisted values are discarded instead of raising or coercing."""
        assert ResetState.from_dict(stored) == ResetState()
