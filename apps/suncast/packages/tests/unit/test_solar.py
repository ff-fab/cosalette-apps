# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for domain/solar.py — Solar position computation.

Test Techniques Used:
- Specification-based Testing: Verifying compute_solar_position contract and SunPosition fields
- Boundary Value Analysis: Polar edge cases (midnight sun, polar night)
- Equivalence Partitioning: Summer/winter solstice as representative seasonal inputs
- Error Guessing: Night-time elevation, extreme latitudes
"""

from __future__ import annotations

import datetime as dt

import pytest

from suncast.domain.solar import SunPosition, compute_solar_position

# ---------------------------------------------------------------------------
# Shared coordinates
# ---------------------------------------------------------------------------

BERLIN_LAT = 52.52
BERLIN_LON = 13.405
BERLIN_TZ = "Europe/Berlin"

TROMSO_LAT = 69.65
TROMSO_LON = 18.96
TROMSO_TZ = "Europe/Oslo"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def berlin_summer_solstice_noon() -> SunPosition:
    """Compute solar position for Berlin at summer solstice noon."""
    at = dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.timezone.utc)
    return compute_solar_position(BERLIN_LAT, BERLIN_LON, BERLIN_TZ, at)


@pytest.fixture()
def berlin_winter_solstice_noon() -> SunPosition:
    """Compute solar position for Berlin at winter solstice noon."""
    at = dt.datetime(2026, 12, 21, 12, 0, tzinfo=dt.timezone.utc)
    return compute_solar_position(BERLIN_LAT, BERLIN_LON, BERLIN_TZ, at)


@pytest.fixture()
def berlin_summer_night() -> SunPosition:
    """Compute solar position for Berlin at 02:00 summer night."""
    at = dt.datetime(2026, 6, 21, 2, 0, tzinfo=dt.timezone.utc)
    return compute_solar_position(BERLIN_LAT, BERLIN_LON, BERLIN_TZ, at)


@pytest.fixture()
def tromso_summer_solstice() -> SunPosition:
    """Compute solar position for Tromsø at summer solstice (midnight sun)."""
    at = dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.timezone.utc)
    return compute_solar_position(TROMSO_LAT, TROMSO_LON, TROMSO_TZ, at)


@pytest.fixture()
def tromso_winter_solstice() -> SunPosition:
    """Compute solar position for Tromsø at winter solstice (polar night)."""
    at = dt.datetime(2026, 12, 21, 12, 0, tzinfo=dt.timezone.utc)
    return compute_solar_position(TROMSO_LAT, TROMSO_LON, TROMSO_TZ, at)


# ---------------------------------------------------------------------------
# Berlin — Summer Solstice
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSolarPositionBerlinSummerSolstice:
    """Specification-based tests: known astronomical values for Berlin summer solstice."""

    def test_azimuth_near_south_at_noon(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Azimuth should be roughly 180° (south) at solar noon."""
        # Arrange — provided via fixture
        result = berlin_summer_solstice_noon

        # Act — computed in fixture

        # Assert
        assert result.azimuth == pytest.approx(180.0, abs=25.0)

    def test_elevation_positive_at_noon(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Elevation should be positive and roughly 60° at summer solstice noon."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert result.elevation > 0
        assert result.elevation == pytest.approx(60.0, abs=5.0)

    def test_is_daylight_true_at_noon(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """is_daylight should be True at noon."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert result.is_daylight is True

    def test_sunrise_sunset_times_exist(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Both sunrise and sunset times should be non-None datetime objects."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert result.sunrise_time is not None
        assert result.sunset_time is not None
        assert isinstance(result.sunrise_time, dt.datetime)
        assert isinstance(result.sunset_time, dt.datetime)

    def test_sunrise_azimuth_northeast(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Sunrise azimuth should be in NE quadrant (~30-80°)."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert result.sunrise_azimuth is not None
        assert 30.0 <= result.sunrise_azimuth <= 80.0

    def test_sunset_azimuth_northwest(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Sunset azimuth should be in NW quadrant (~280-330°)."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert result.sunset_azimuth is not None
        assert 280.0 <= result.sunset_azimuth <= 330.0


# ---------------------------------------------------------------------------
# Berlin — Winter Solstice
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSolarPositionBerlinWinterSolstice:
    """Specification-based tests: seasonal comparison for Berlin winter solstice."""

    def test_elevation_lower_than_summer(
        self, berlin_winter_solstice_noon: SunPosition
    ) -> None:
        """Elevation at noon should be roughly 14°, much lower than summer."""
        # Arrange
        result = berlin_winter_solstice_noon

        # Assert
        assert result.elevation == pytest.approx(14.0, abs=5.0)

    def test_is_daylight_true_at_noon(
        self, berlin_winter_solstice_noon: SunPosition
    ) -> None:
        """Still daylight at noon in Berlin even in winter."""
        # Arrange
        result = berlin_winter_solstice_noon

        # Assert
        assert result.is_daylight is True

    def test_sunrise_sunset_times_exist(
        self, berlin_winter_solstice_noon: SunPosition
    ) -> None:
        """Both sunrise and sunset should exist (Berlin is not polar)."""
        # Arrange
        result = berlin_winter_solstice_noon

        # Assert
        assert result.sunrise_time is not None
        assert result.sunset_time is not None


# ---------------------------------------------------------------------------
# Hourly Azimuths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHourlyAzimuths:
    """Specification-based tests: verifying hourly azimuths array contract."""

    def test_hourly_azimuths_has_24_entries(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """hourly_azimuths should contain exactly 24 entries."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert len(result.hourly_azimuths) == 24

    def test_hourly_azimuths_all_in_range(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """All hourly azimuth values should be between 0 and 360."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        for azimuth in result.hourly_azimuths:
            assert 0.0 <= azimuth <= 360.0

    def test_hourly_azimuths_are_tuple(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """hourly_azimuths should be a tuple (immutable)."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        assert isinstance(result.hourly_azimuths, tuple)


# ---------------------------------------------------------------------------
# Night Time
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNightTime:
    """Error guessing tests: verifying night-time behavior."""

    def test_elevation_negative_at_night(
        self, berlin_summer_night: SunPosition
    ) -> None:
        """Elevation should be negative at 02:00 in summer."""
        # Arrange
        result = berlin_summer_night

        # Assert
        assert result.elevation < 0

    def test_is_daylight_false_at_night(self, berlin_summer_night: SunPosition) -> None:
        """is_daylight should be False at 02:00."""
        # Arrange
        result = berlin_summer_night

        # Assert
        assert result.is_daylight is False


# ---------------------------------------------------------------------------
# Polar Day (Midnight Sun) — Tromsø
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPolarDayMidnightSun:
    """Boundary value analysis: extreme latitude during midnight sun period."""

    def test_no_sunrise_sunset_during_polar_day(
        self, tromso_summer_solstice: SunPosition
    ) -> None:
        """sunrise_time and sunset_time should be None during midnight sun."""
        # Arrange
        result = tromso_summer_solstice

        # Assert
        assert result.sunrise_time is None
        assert result.sunset_time is None

    def test_sunrise_sunset_azimuths_none(
        self, tromso_summer_solstice: SunPosition
    ) -> None:
        """sunrise_azimuth and sunset_azimuth should be None during midnight sun."""
        # Arrange
        result = tromso_summer_solstice

        # Assert
        assert result.sunrise_azimuth is None
        assert result.sunset_azimuth is None

    def test_elevation_positive(self, tromso_summer_solstice: SunPosition) -> None:
        """Elevation should still be positive during midnight sun."""
        # Arrange
        result = tromso_summer_solstice

        # Assert
        assert result.elevation > 0

    def test_hourly_azimuths_still_computed(
        self, tromso_summer_solstice: SunPosition
    ) -> None:
        """Hourly azimuths should still have 24 entries even during polar day."""
        # Arrange
        result = tromso_summer_solstice

        # Assert
        assert len(result.hourly_azimuths) == 24


# ---------------------------------------------------------------------------
# Polar Night — Tromsø
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPolarNight:
    """Boundary value analysis: polar night edge case."""

    def test_no_sunrise_sunset_during_polar_night(
        self, tromso_winter_solstice: SunPosition
    ) -> None:
        """Both sunrise_time and sunset_time should be None during polar night."""
        # Arrange
        result = tromso_winter_solstice

        # Assert
        assert result.sunrise_time is None
        assert result.sunset_time is None

    def test_elevation_negative_or_very_low(
        self, tromso_winter_solstice: SunPosition
    ) -> None:
        """Elevation should be negative or near zero during polar night."""
        # Arrange
        result = tromso_winter_solstice

        # Assert
        assert result.elevation <= 1.0

    def test_is_daylight_false(self, tromso_winter_solstice: SunPosition) -> None:
        """is_daylight should be False during polar night."""
        # Arrange
        result = tromso_winter_solstice

        # Assert
        assert result.is_daylight is False


# ---------------------------------------------------------------------------
# SunPosition Dataclass Contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSunPositionDataclass:
    """Specification-based tests: dataclass contract verification."""

    def test_frozen_immutability(
        self, berlin_summer_solstice_noon: SunPosition
    ) -> None:
        """Assigning to a field on a frozen dataclass should raise an error."""
        # Arrange
        result = berlin_summer_solstice_noon

        # Assert
        with pytest.raises(AttributeError):
            result.azimuth = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Naive Datetime Input
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNaiveDatetimeInput:
    """Specification-based tests: naive datetime is interpreted in the given timezone."""

    def test_naive_datetime_matches_aware(self) -> None:
        """A naive datetime should produce the same result as an aware one in the same tz."""
        # Arrange
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(BERLIN_TZ)
        naive = dt.datetime(2026, 6, 21, 14, 0)
        aware = dt.datetime(2026, 6, 21, 14, 0, tzinfo=tz)

        # Act
        result_naive = compute_solar_position(BERLIN_LAT, BERLIN_LON, BERLIN_TZ, naive)
        result_aware = compute_solar_position(BERLIN_LAT, BERLIN_LON, BERLIN_TZ, aware)

        # Assert
        assert result_naive.azimuth == pytest.approx(result_aware.azimuth, abs=0.01)
        assert result_naive.elevation == pytest.approx(result_aware.elevation, abs=0.01)
