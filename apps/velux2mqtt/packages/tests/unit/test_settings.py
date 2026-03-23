"""Unit tests for Velux2MqttSettings and CoverConfig.

Test Techniques Used:
- Boundary Value Analysis: GPIO pin range (0–27), travel duration (gt=0)
- Equivalence Partitioning: Valid/invalid setting combinations
- Specification-based Testing: Default values match documented behavior
"""

import pytest
from pydantic import ValidationError

from velux2mqtt.settings import CoverConfig, Velux2MqttSettings


# -- CoverConfig --


class TestCoverConfig:
    """Tests for individual cover configuration validation."""

    def test_valid_cover(self) -> None:
        """A cover with distinct valid pins and positive durations is accepted."""
        cover = CoverConfig(
            name="blind",
            pin_up=9,
            pin_stop=10,
            pin_down=11,
            travel_duration_up=18.5,
            travel_duration_down=18.5,
        )

        assert cover.name == "blind"
        assert cover.pin_up == 9
        assert cover.travel_time_offset == 1.0
        assert cover.max_timer_margin == 2.0
        assert cover.measure_offset is True
        assert cover.dead_band_pct == 0.0

    def test_measure_offset_false(self) -> None:
        """Cover with measure_offset=False is accepted.

        Technique: Specification-based — optional boolean field.
        """
        cover = CoverConfig(
            name="blind",
            pin_up=9,
            pin_stop=10,
            pin_down=11,
            travel_duration_up=18.5,
            travel_duration_down=18.5,
            measure_offset=False,
        )
        assert cover.measure_offset is False

    def test_duplicate_pins_rejected(self) -> None:
        """Covers must have three distinct GPIO pins."""
        with pytest.raises(ValidationError, match="must be distinct"):
            CoverConfig(
                name="bad",
                pin_up=9,
                pin_stop=9,
                pin_down=11,
                travel_duration_up=18.0,
                travel_duration_down=18.0,
            )

    def test_pin_out_of_range(self) -> None:
        """GPIO pins must be 0–27 (BCM range)."""
        with pytest.raises(ValidationError):
            CoverConfig(
                name="bad",
                pin_up=28,
                pin_stop=10,
                pin_down=11,
                travel_duration_up=18.0,
                travel_duration_down=18.0,
            )

    def test_negative_duration_rejected(self) -> None:
        """Travel durations must be positive."""
        with pytest.raises(ValidationError):
            CoverConfig(
                name="bad",
                pin_up=9,
                pin_stop=10,
                pin_down=11,
                travel_duration_up=-1.0,
                travel_duration_down=18.0,
            )

    def test_dead_band_pct_valid(self) -> None:
        """Dead band percentage between 0 and 100 is accepted.

        Technique: Boundary Value Analysis — dead_band_pct valid range.
        """
        cover = CoverConfig(
            name="window",
            pin_up=9,
            pin_stop=10,
            pin_down=11,
            travel_duration_up=20.0,
            travel_duration_down=20.0,
            dead_band_pct=15.0,
        )
        assert cover.dead_band_pct == 15.0

    def test_dead_band_pct_negative_rejected(self) -> None:
        """Negative dead band percentage is rejected.

        Technique: Boundary Value Analysis — below minimum.
        """
        with pytest.raises(ValidationError):
            CoverConfig(
                name="bad",
                pin_up=9,
                pin_stop=10,
                pin_down=11,
                travel_duration_up=20.0,
                travel_duration_down=20.0,
                dead_band_pct=-1.0,
            )

    def test_dead_band_pct_100_rejected(self) -> None:
        """Dead band percentage of 100 is rejected (lt=100).

        Technique: Boundary Value Analysis — at exclusive upper bound.
        """
        with pytest.raises(ValidationError):
            CoverConfig(
                name="bad",
                pin_up=9,
                pin_stop=10,
                pin_down=11,
                travel_duration_up=20.0,
                travel_duration_down=20.0,
                dead_band_pct=100.0,
            )


# -- Velux2MqttSettings --


class TestVelux2MqttSettings:
    """Tests for the top-level settings model."""

    def test_defaults_no_covers(self) -> None:
        """Settings with no covers are valid (empty list)."""
        settings = Velux2MqttSettings(covers=[])

        assert settings.covers == []
        assert settings.button_press_duration == 0.5
        assert settings.enable_startup_homing is True
        assert settings.homing_direction == "close"
        assert settings.calibration_runs == 3
        assert settings.drift_recalibration_threshold == 2

    def test_two_covers_valid(self) -> None:
        """Two covers with non-overlapping pins are accepted."""
        settings = Velux2MqttSettings(
            covers=[
                CoverConfig(
                    name="blind",
                    pin_up=9,
                    pin_stop=10,
                    pin_down=11,
                    travel_duration_up=18.5,
                    travel_duration_down=18.5,
                ),
                CoverConfig(
                    name="window",
                    pin_up=23,
                    pin_stop=24,
                    pin_down=25,
                    travel_duration_up=20.0,
                    travel_duration_down=20.0,
                ),
            ],
        )

        assert len(settings.covers) == 2
        assert settings.covers[0].name == "blind"
        assert settings.covers[1].name == "window"

    def test_duplicate_cover_names_rejected(self) -> None:
        """Cover names must be unique."""
        with pytest.raises(ValidationError, match="unique"):
            Velux2MqttSettings(
                covers=[
                    CoverConfig(
                        name="blind",
                        pin_up=9,
                        pin_stop=10,
                        pin_down=11,
                        travel_duration_up=18.0,
                        travel_duration_down=18.0,
                    ),
                    CoverConfig(
                        name="blind",
                        pin_up=23,
                        pin_stop=24,
                        pin_down=25,
                        travel_duration_up=18.0,
                        travel_duration_down=18.0,
                    ),
                ],
            )

    def test_overlapping_pins_across_covers_rejected(self) -> None:
        """GPIO pins must not overlap between covers."""
        with pytest.raises(ValidationError, match="GPIO pin"):
            Velux2MqttSettings(
                covers=[
                    CoverConfig(
                        name="blind",
                        pin_up=9,
                        pin_stop=10,
                        pin_down=11,
                        travel_duration_up=18.0,
                        travel_duration_down=18.0,
                    ),
                    CoverConfig(
                        name="window",
                        pin_up=9,
                        pin_stop=24,
                        pin_down=25,
                        travel_duration_up=18.0,
                        travel_duration_down=18.0,
                    ),
                ],
            )

    def test_homing_direction_validated(self) -> None:
        """Homing direction must be 'open' or 'close'."""
        with pytest.raises(ValidationError):
            Velux2MqttSettings(covers=[], homing_direction="sideways")  # type: ignore[arg-type]

    def test_calibration_runs_minimum(self) -> None:
        """Calibration runs must be at least 1."""
        with pytest.raises(ValidationError):
            Velux2MqttSettings(covers=[], calibration_runs=0)

    def test_drift_threshold_zero_disables(self) -> None:
        """A threshold of 0 is valid (disables drift compensation)."""
        settings = Velux2MqttSettings(
            covers=[],
            drift_recalibration_threshold=0,
        )

        assert settings.drift_recalibration_threshold == 0
