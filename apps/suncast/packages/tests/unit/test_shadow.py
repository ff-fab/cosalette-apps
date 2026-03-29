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

"""Unit tests for domain/shadow.py — Shadow projection geometry.

Test Techniques Used:
- Equivalence Partitioning: Sun position classes (daylight, night, overhead)
- Boundary Value Analysis: Sun elevation at 0° and 90° boundaries
- Specification-based: Compass azimuth to cartesian conversion
"""

from __future__ import annotations

import math

import pytest

from suncast.domain.geometry import BuildingConfig, CanvasConfig, GeometryConfig
from suncast.domain.shadow import (
    Point,
    ShadowResult,
    apply_north_rotation,
    clip_to_circle,
    compute_building_shadows,
    compute_shadow_polygon,
    degrees_to_cartesian,
)
from suncast.domain.solar import SunPosition


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_geometry() -> GeometryConfig:
    """A simple geometry with one shadow-casting building and one non-casting."""
    return GeometryConfig(
        canvas=CanvasConfig(size=100, north_rotation=0.0),
        buildings=[
            BuildingConfig(
                name="house",
                vertices=[(40, 40), (60, 40), (60, 60), (40, 60)],
                casts_shadow=True,
            ),
            BuildingConfig(
                name="shed",
                vertices=[(10, 10), (20, 10), (20, 20)],
                casts_shadow=False,
            ),
        ],
    )


@pytest.fixture()
def daylight_sun() -> SunPosition:
    """A sun position representing mid-day conditions."""
    return SunPosition(
        azimuth=180.0,
        elevation=45.0,
        sunrise_azimuth=90.0,
        sunset_azimuth=270.0,
        sunrise_time=None,
        sunset_time=None,
        hourly_azimuths=tuple(range(24)),
        is_daylight=True,
    )


@pytest.fixture()
def night_sun() -> SunPosition:
    """A sun position representing night-time (below horizon)."""
    return SunPosition(
        azimuth=0.0,
        elevation=-10.0,
        sunrise_azimuth=None,
        sunset_azimuth=None,
        sunrise_time=None,
        sunset_time=None,
        hourly_azimuths=tuple(range(24)),
        is_daylight=False,
    )


# ---------------------------------------------------------------------------
# degrees_to_cartesian
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDegreesToCartesian:
    """Specification-based: compass azimuth to canvas coordinate conversion."""

    def test_north_azimuth_moves_up(self) -> None:
        """Azimuth 0° (north) should decrease y."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = degrees_to_cartesian(0, 10, center)

        # Assert
        assert result.x == pytest.approx(50, abs=1e-10)
        assert result.y == pytest.approx(40, abs=1e-10)

    def test_east_azimuth_moves_right(self) -> None:
        """Azimuth 90° (east) should increase x."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = degrees_to_cartesian(90, 10, center)

        # Assert
        assert result.x == pytest.approx(60, abs=1e-10)
        assert result.y == pytest.approx(50, abs=1e-10)

    def test_south_azimuth_moves_down(self) -> None:
        """Azimuth 180° (south) should increase y."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = degrees_to_cartesian(180, 10, center)

        # Assert
        assert result.x == pytest.approx(50, abs=1e-10)
        assert result.y == pytest.approx(60, abs=1e-10)

    def test_west_azimuth_moves_left(self) -> None:
        """Azimuth 270° (west) should decrease x."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = degrees_to_cartesian(270, 10, center)

        # Assert
        assert result.x == pytest.approx(40, abs=1e-10)
        assert result.y == pytest.approx(50, abs=1e-10)


# ---------------------------------------------------------------------------
# apply_north_rotation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyNorthRotation:
    """Equivalence Partitioning: north rotation adjustment."""

    @pytest.mark.parametrize(
        ("azimuth", "rotation", "expected"),
        [
            (180, 0, 180),
            (180, 30, 150),
            (10, 20, 350),
        ],
        ids=["identity", "positive-rotation", "negative-wrap"],
    )
    def test_rotation_cases(
        self, azimuth: float, rotation: float, expected: float
    ) -> None:
        """Verify north rotation adjustment for various cases."""
        # Act
        result = apply_north_rotation(azimuth, rotation)

        # Assert
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# compute_shadow_polygon
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeShadowPolygon:
    """Boundary Value Analysis + Equivalence Partitioning for shadow polygon computation."""

    def test_sun_below_horizon_returns_empty(self) -> None:
        """Elevation <= 0 should produce no shadow."""
        # Arrange
        vertices = [(40, 40), (60, 40), (60, 60), (40, 60)]

        # Act
        result = compute_shadow_polygon(vertices, 180, 0, 100)

        # Assert
        assert result == []

    def test_sun_at_zenith_returns_empty(self) -> None:
        """Elevation >= 90 should produce no shadow."""
        # Arrange
        vertices = [(40, 40), (60, 40), (60, 60), (40, 60)]

        # Act
        result = compute_shadow_polygon(vertices, 180, 90, 100)

        # Assert
        assert result == []

    def test_sun_nearly_overhead_produces_short_shadow(self) -> None:
        """Elevation near 90° should produce a very short shadow."""
        # Arrange
        vertices = [(40, 40), (60, 40), (60, 60), (40, 60)]

        # Act
        result = compute_shadow_polygon(vertices, 180, 89.99, 100)

        # Assert
        assert len(result) == 8  # 4 base + 4 projected
        # Shadow should be very short — projected points close to base
        for base, proj in zip(result[:4], reversed(result[4:]), strict=True):
            assert abs(base.x - proj.x) < 1.0
            assert abs(base.y - proj.y) < 1.0

    def test_elevation_45_produces_reasonable_shadow(self) -> None:
        """At 45° elevation, shadow length factor is 1.0, scaled by canvas_size*0.5."""
        # Arrange
        vertices = [(50, 50), (60, 50), (60, 60), (50, 60)]

        # Act
        result = compute_shadow_polygon(vertices, 180, 45, 100)

        # Assert
        assert len(result) == 8
        # tan(45°) = 1.0, so shadow_length = 1.0 * 100 * 0.5 = 50
        # Shadow direction is (180+180)%360 = 0° (north), so y decreases by 50
        projected_first = result[7]  # reversed projected, first base -> last projected
        assert projected_first.y == pytest.approx(50 - 50, abs=0.1)

    def test_fewer_than_three_vertices_returns_empty(self) -> None:
        """Fewer than 3 vertices should return empty polygon."""
        # Arrange
        vertices = [(10, 10), (20, 20)]

        # Act
        result = compute_shadow_polygon(vertices, 180, 45, 100)

        # Assert
        assert result == []

    def test_rectangle_produces_eight_point_polygon(self) -> None:
        """A rectangle (4 vertices) should produce an 8-point shadow polygon."""
        # Arrange
        vertices = [(30, 30), (70, 30), (70, 70), (30, 70)]

        # Act
        result = compute_shadow_polygon(vertices, 90, 30, 100)

        # Assert
        assert len(result) == 8


# ---------------------------------------------------------------------------
# clip_to_circle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClipToCircle:
    """Boundary Value Analysis: circle clipping of polygon points."""

    def test_points_inside_circle_unchanged(self) -> None:
        """Points within the circle should not be modified."""
        # Arrange
        center = Point(50, 50)
        polygon = [Point(50, 50), Point(55, 50), Point(50, 55)]

        # Act
        result = clip_to_circle(polygon, center, 50)

        # Assert
        assert result == polygon

    def test_point_outside_circle_clamped(self) -> None:
        """A point outside the circle should be clamped to the boundary."""
        # Arrange
        center = Point(50, 50)
        polygon = [Point(150, 50)]  # 100 units to the right, radius is 50

        # Act
        result = clip_to_circle(polygon, center, 50)

        # Assert
        assert result[0].x == pytest.approx(100, abs=1e-10)
        assert result[0].y == pytest.approx(50, abs=1e-10)

    def test_empty_polygon_returns_empty(self) -> None:
        """An empty polygon should return an empty list."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = clip_to_circle([], center, 50)

        # Assert
        assert result == []

    def test_point_on_boundary_unchanged(self) -> None:
        """A point exactly on the boundary should not be modified."""
        # Arrange
        center = Point(50, 50)
        polygon = [Point(100, 50)]  # exactly radius=50 away

        # Act
        result = clip_to_circle(polygon, center, 50)

        # Assert
        assert result[0].x == pytest.approx(100, abs=1e-10)
        assert result[0].y == pytest.approx(50, abs=1e-10)

    def test_diagonal_point_clamped_correctly(self) -> None:
        """A point outside the circle diagonally should be clamped along the vector."""
        # Arrange
        center = Point(0, 0)
        # Point at (100, 100), distance = sqrt(20000) ~ 141.4
        polygon = [Point(100, 100)]

        # Act
        result = clip_to_circle(polygon, center, 50)

        # Assert
        dist = math.hypot(result[0].x, result[0].y)
        assert dist == pytest.approx(50, abs=1e-10)


# ---------------------------------------------------------------------------
# compute_building_shadows
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeBuildingShadows:
    """Specification-based: integration of shadow pipeline components."""

    def test_sun_below_horizon_returns_empty(
        self, sample_geometry: GeometryConfig, night_sun: SunPosition
    ) -> None:
        """No shadows when the sun is below the horizon."""
        # Act
        result = compute_building_shadows(sample_geometry, night_sun)

        # Assert
        assert result == []

    def test_building_without_casts_shadow_skipped(
        self, sample_geometry: GeometryConfig, daylight_sun: SunPosition
    ) -> None:
        """Buildings with casts_shadow=False should not appear in results."""
        # Act
        result = compute_building_shadows(sample_geometry, daylight_sun)

        # Assert
        names = [r.building_name for r in result]
        assert "shed" not in names

    def test_normal_case_produces_shadow_result(
        self, sample_geometry: GeometryConfig, daylight_sun: SunPosition
    ) -> None:
        """A shadow-casting building in daylight should produce a ShadowResult."""
        # Act
        result = compute_building_shadows(sample_geometry, daylight_sun)

        # Assert
        assert len(result) == 1
        assert result[0].building_name == "house"
        assert len(result[0].shadow_polygon) > 0

    def test_shadow_result_type(
        self, sample_geometry: GeometryConfig, daylight_sun: SunPosition
    ) -> None:
        """Results should be ShadowResult instances with Point polygons."""
        # Act
        result = compute_building_shadows(sample_geometry, daylight_sun)

        # Assert
        assert isinstance(result[0], ShadowResult)
        assert all(isinstance(p, Point) for p in result[0].shadow_polygon)
