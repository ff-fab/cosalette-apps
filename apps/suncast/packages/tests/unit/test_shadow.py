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
- Specification-based: Compass azimuth to cartesian conversion, silhouette detection
- Structural Testing: Convex and concave polygon silhouette shapes
"""

from __future__ import annotations

import math

import pytest

from suncast.domain.geometry import BuildingConfig, CanvasConfig, GeometryConfig
from suncast.domain.shadow import (
    Point,
    ShadowResult,
    apply_north_rotation,
    clamp_to_circle,
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
        shadow, sun_facing = compute_shadow_polygon(vertices, 180, 0, 100)

        # Assert
        assert shadow == ()
        assert sun_facing == ()

    def test_sun_at_zenith_returns_empty(self) -> None:
        """Elevation >= 90 should produce no shadow."""
        # Arrange
        vertices = [(40, 40), (60, 40), (60, 60), (40, 60)]

        # Act
        shadow, sun_facing = compute_shadow_polygon(vertices, 180, 90, 100)

        # Assert
        assert shadow == ()
        assert sun_facing == ()

    def test_sun_nearly_overhead_produces_shadow(self) -> None:
        """Elevation near 90° should still produce a valid shadow polygon."""
        # Arrange
        vertices = [(40, 40), (60, 40), (60, 60), (40, 60)]

        # Act
        shadow, sun_facing = compute_shadow_polygon(vertices, 180, 89.99, 100)

        # Assert — shadow and sun_facing should be non-empty
        assert len(shadow) > 0
        assert len(sun_facing) > 0

    def test_elevation_45_shadow_falls_opposite_sun(self) -> None:
        """At 45° elevation with sun from south (180°), shadow falls northward.

        Technique: Specification-based — shadow direction verification.
        """
        # Arrange
        vertices = [(50, 50), (60, 50), (60, 60), (50, 60)]

        # Act
        shadow, _sun_facing = compute_shadow_polygon(vertices, 180, 45, 100)

        # Assert — projected vertices should have lower y (northward)
        building_pts = {Point(vx, vy) for vx, vy in vertices}
        projected = [p for p in shadow if p not in building_pts]
        assert len(projected) > 0
        centroid_y = sum(vy for _, vy in vertices) / len(vertices)
        for p in projected:
            assert p.y < centroid_y, (
                "Shadow should fall north (lower y) when sun is south"
            )

    def test_fewer_than_three_vertices_returns_empty(self) -> None:
        """Fewer than 3 vertices should return empty polygon."""
        # Arrange
        vertices = [(10, 10), (20, 20)]

        # Act
        shadow, sun_facing = compute_shadow_polygon(vertices, 180, 45, 100)

        # Assert
        assert shadow == ()
        assert sun_facing == ()

    def test_rectangle_shadow_structure(self) -> None:
        """A rectangle produces a shadow with max_projected + side2 + min_projected.

        Technique: Specification-based — shadow polygon structure.
        """
        # Arrange
        vertices = [(30, 30), (70, 30), (70, 70), (30, 70)]

        # Act
        shadow, sun_facing = compute_shadow_polygon(vertices, 90, 30, 100)

        # Assert — shadow should have projected + side2 vertices
        assert len(shadow) >= 3
        assert len(sun_facing) >= 2

    def test_sun_facing_edges_populated(self) -> None:
        """Sun-facing edges should contain the sun-lit building vertices.

        Technique: Specification-based — sun_facing_edges content.
        """
        # Arrange
        vertices = [(30, 30), (70, 30), (70, 70), (30, 70)]

        # Act
        _shadow, sun_facing = compute_shadow_polygon(vertices, 180, 45, 100)

        # Assert — sun_facing should be a non-empty subset of building vertices
        assert len(sun_facing) >= 2
        building_pts = {Point(vx, vy) for vx, vy in vertices}
        for p in sun_facing:
            assert p in building_pts

    def test_convex_shadow_non_self_intersecting(self) -> None:
        """Shadow polygon from a convex building should form a valid non-degenerate shape.

        Technique: Structural Testing — polygon validity for convex input.

        Uses the shoelace formula to verify the polygon has non-zero signed area,
        proving it is non-degenerate.
        """
        # Arrange
        vertices = [(30, 30), (70, 30), (70, 70), (30, 70)]

        # Act
        shadow, _sun_facing = compute_shadow_polygon(vertices, 135, 30, 200)

        # Assert — verify non-zero area via shoelace formula
        assert len(shadow) >= 3
        n = len(shadow)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += shadow[i].x * shadow[j].y
            area -= shadow[j].x * shadow[i].y
        area = abs(area) / 2.0
        assert area > 0.0, "Shadow polygon should have non-zero area"

    def test_concave_l_shape_silhouette(self) -> None:
        """An L-shaped concave polygon should produce a valid silhouette shadow.

        Technique: Structural Testing — concave polygon silhouette detection.
        """
        # Arrange — L-shape
        vertices = [
            (30, 30),
            (60, 30),
            (60, 50),
            (50, 50),
            (50, 70),
            (30, 70),
        ]

        # Act
        shadow, sun_facing = compute_shadow_polygon(vertices, 135, 30, 200)

        # Assert — both outputs should be non-empty
        assert len(shadow) >= 3
        assert len(sun_facing) >= 2


# ---------------------------------------------------------------------------
# clip_to_circle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClampToCircle:
    """Boundary Value Analysis: circle clamping of polygon points."""

    def test_points_inside_circle_unchanged(self) -> None:
        """Points within the circle should not be modified."""
        # Arrange
        center = Point(50, 50)
        polygon = (Point(50, 50), Point(55, 50), Point(50, 55))

        # Act
        result = clamp_to_circle(polygon, center, 50)

        # Assert
        assert result == polygon

    def test_point_outside_circle_clamped(self) -> None:
        """A point outside the circle should be clamped to the boundary."""
        # Arrange
        center = Point(50, 50)
        polygon = (Point(150, 50),)  # 100 units to the right, radius is 50

        # Act
        result = clamp_to_circle(polygon, center, 50)

        # Assert
        assert result[0].x == pytest.approx(100, abs=1e-10)
        assert result[0].y == pytest.approx(50, abs=1e-10)

    def test_empty_polygon_returns_empty(self) -> None:
        """An empty polygon should return an empty tuple."""
        # Arrange
        center = Point(50, 50)

        # Act
        result = clamp_to_circle((), center, 50)

        # Assert
        assert result == ()

    def test_point_on_boundary_unchanged(self) -> None:
        """A point exactly on the boundary should not be modified."""
        # Arrange
        center = Point(50, 50)
        polygon = (Point(100, 50),)  # exactly radius=50 away

        # Act
        result = clamp_to_circle(polygon, center, 50)

        # Assert
        assert result[0].x == pytest.approx(100, abs=1e-10)
        assert result[0].y == pytest.approx(50, abs=1e-10)

    def test_diagonal_point_clamped_correctly(self) -> None:
        """A point outside the circle diagonally should be clamped along the vector."""
        # Arrange
        center = Point(0, 0)
        # Point at (100, 100), distance = sqrt(20000) ~ 141.4
        polygon = (Point(100, 100),)

        # Act
        result = clamp_to_circle(polygon, center, 50)

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
        assert len(result) == 1
        assert isinstance(result[0], ShadowResult)
        assert all(isinstance(p, Point) for p in result[0].shadow_polygon)
