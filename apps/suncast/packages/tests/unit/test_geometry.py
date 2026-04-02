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

"""Unit tests for domain/geometry.py — YAML/JSON geometry loader.

Test Techniques Used:
- Specification-based Testing: Verifying model contracts and load_geometry behavior
- Boundary Value Analysis: Vertices at canvas edges (0 and size), just outside bounds
- Equivalence Partitioning: Valid YAML, valid JSON, invalid extension
- Error Guessing: Empty buildings list, fewer than 3 vertices, missing file
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from suncast.domain.geometry import (
    BuildingConfig,
    CanvasConfig,
    GeometryConfig,
    HighlightedRegion,
    fit_to_circle,
    load_geometry,
)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

MINIMAL_YAML = """\
buildings:
  - name: house
    vertices:
      - [0, 0]
      - [10, 0]
      - [10, 10]
"""

FULL_YAML = """\
canvas:
  size: 200
  north_rotation: 15.5
buildings:
  - name: tower
    vertices:
      - [10, 10]
      - [30, 10]
      - [30, 40]
      - [10, 40]
    casts_shadow: true
    style: home
  - name: shed
    vertices:
      - [100, 100]
      - [120, 100]
      - [120, 110]
    casts_shadow: false
    style: neighbor
highlighted_regions:
  - name: garden
    vertices:
      - [50, 50]
      - [80, 50]
      - [80, 70]
      - [50, 70]
    color: "#00ff00"
"""

MINIMAL_JSON = """\
{
  "buildings": [
    {
      "name": "box",
      "vertices": [[0, 0], [50, 0], [50, 50]]
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# CanvasConfig defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCanvasConfigDefaults:
    """Specification-based: verify CanvasConfig default values and immutability."""

    def test_default_size_is_100(self) -> None:
        """Default canvas size should be 100."""
        # Arrange / Act
        canvas = CanvasConfig()

        # Assert
        assert canvas.size == 100

    def test_default_north_rotation_is_zero(self) -> None:
        """Default north_rotation should be 0.0."""
        # Arrange / Act
        canvas = CanvasConfig()

        # Assert
        assert canvas.north_rotation == 0.0

    def test_custom_size(self) -> None:
        """Canvas size can be overridden."""
        # Arrange / Act
        canvas = CanvasConfig(size=200)

        # Assert
        assert canvas.size == 200

    def test_custom_north_rotation(self) -> None:
        """north_rotation can be overridden."""
        # Arrange / Act
        canvas = CanvasConfig(north_rotation=45.0)

        # Assert
        assert canvas.north_rotation == 45.0

    def test_size_must_be_positive(self) -> None:
        """Canvas size <= 0 should raise ValidationError."""
        # Act / Assert
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            CanvasConfig(size=0)

    def test_frozen_immutability(self) -> None:
        """Assigning to a frozen model field should raise an error."""
        # Arrange
        canvas = CanvasConfig()

        # Assert
        with pytest.raises(ValidationError):
            canvas.size = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BuildingConfig construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildingConfigConstruction:
    """Specification-based: verify BuildingConfig fields."""

    def test_basic_construction(self) -> None:
        """A BuildingConfig stores name and vertices."""
        # Arrange / Act
        building = BuildingConfig(
            name="house",
            vertices=[(0, 0), (10, 0), (10, 10)],
        )

        # Assert
        assert building.name == "house"
        assert len(building.vertices) == 3

    def test_default_casts_shadow_true(self) -> None:
        """casts_shadow defaults to True."""
        # Arrange / Act
        building = BuildingConfig(name="house", vertices=[(0, 0), (1, 0), (1, 1)])

        # Assert
        assert building.casts_shadow is True

    def test_default_style_is_default(self) -> None:
        """style defaults to 'default'."""
        # Arrange / Act
        building = BuildingConfig(name="house", vertices=[(0, 0), (1, 0), (1, 1)])

        # Assert
        assert building.style == "default"

    def test_custom_style_and_casts_shadow(self) -> None:
        """casts_shadow and style can be overridden."""
        # Arrange / Act
        building = BuildingConfig(
            name="garage",
            vertices=[(0, 0), (5, 0), (5, 5)],
            casts_shadow=False,
            style="neighbor",
        )

        # Assert
        assert building.casts_shadow is False
        assert building.style == "neighbor"

    def test_float_vertices(self) -> None:
        """Vertices accept float coordinates."""
        # Arrange / Act
        building = BuildingConfig(
            name="precise",
            vertices=[(0.5, 1.25), (10.75, 0.0), (10.75, 10.5)],
        )

        # Assert
        assert building.vertices[0] == (0.5, 1.25)

    def test_frozen_immutability(self) -> None:
        """Assigning to a frozen model field should raise an error."""
        # Arrange
        building = BuildingConfig(name="house", vertices=[(0, 0), (1, 0), (1, 1)])

        # Assert
        with pytest.raises(ValidationError):
            building.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HighlightedRegion construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHighlightedRegionConstruction:
    """Specification-based: verify HighlightedRegion fields."""

    def test_basic_construction(self) -> None:
        """A HighlightedRegion stores name, vertices, and color."""
        # Arrange / Act
        region = HighlightedRegion(
            name="patio",
            vertices=[(0, 0), (10, 0), (10, 10)],
            color="#ff0000",
        )

        # Assert
        assert region.name == "patio"
        assert len(region.vertices) == 3
        assert region.color == "#ff0000"


# ---------------------------------------------------------------------------
# load_geometry — YAML
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadGeometryFromYaml:
    """Specification-based: loading geometry from YAML files."""

    def test_minimal_yaml(self, tmp_path: Path) -> None:
        """Minimal YAML with one building should load with default canvas."""
        # Arrange
        f = tmp_path / "scene.yaml"
        f.write_text(MINIMAL_YAML)

        # Act
        config = load_geometry(f)

        # Assert
        assert config.canvas.size == 100
        assert config.canvas.north_rotation == 0.0
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "house"
        assert config.buildings[0].casts_shadow is True
        assert config.buildings[0].style == "default"
        assert config.highlighted_regions == []

    def test_full_yaml(self, tmp_path: Path) -> None:
        """Full YAML with custom canvas, multiple buildings, and highlights."""
        # Arrange
        f = tmp_path / "scene.yml"
        f.write_text(FULL_YAML)

        # Act
        config = load_geometry(f)

        # Assert
        assert config.canvas.size == 200
        assert config.canvas.north_rotation == 15.5
        assert len(config.buildings) == 2
        assert config.buildings[0].name == "tower"
        assert config.buildings[0].casts_shadow is True
        assert config.buildings[0].style == "home"
        assert config.buildings[1].name == "shed"
        assert config.buildings[1].casts_shadow is False
        assert config.buildings[1].style == "neighbor"
        assert len(config.highlighted_regions) == 1
        assert config.highlighted_regions[0].name == "garden"
        assert config.highlighted_regions[0].color == "#00ff00"
        assert len(config.highlighted_regions[0].vertices) == 4


# ---------------------------------------------------------------------------
# load_geometry — JSON
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadGeometryFromJson:
    """Specification-based: loading geometry from JSON files."""

    def test_minimal_json(self, tmp_path: Path) -> None:
        """Minimal JSON should load correctly."""
        # Arrange
        f = tmp_path / "scene.json"
        f.write_text(MINIMAL_JSON)

        # Act
        config = load_geometry(f)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "box"


# ---------------------------------------------------------------------------
# load_geometry — validation errors
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadGeometryValidation:
    """Error guessing and boundary analysis: invalid inputs."""

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        """Unsupported file extension should raise ValueError."""
        # Arrange
        f = tmp_path / "scene.toml"
        f.write_text("x = 1")

        # Act / Assert
        with pytest.raises(ValueError, match="Unsupported file extension"):
            load_geometry(f)

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Missing file should raise FileNotFoundError."""
        # Arrange
        f = tmp_path / "missing.yaml"

        # Act / Assert
        with pytest.raises(FileNotFoundError):
            load_geometry(f)

    def test_no_buildings_raises(self, tmp_path: Path) -> None:
        """Empty buildings list should raise ValueError."""
        # Arrange
        f = tmp_path / "empty.yaml"
        f.write_text("buildings: []\n")

        # Act / Assert
        with pytest.raises(ValueError, match="At least one building"):
            load_geometry(f)

    def test_fewer_than_three_vertices(self, tmp_path: Path) -> None:
        """A building with fewer than 3 vertices should raise ValueError."""
        # Arrange
        content = """\
buildings:
  - name: line
    vertices:
      - [0, 0]
      - [10, 0]
"""
        f = tmp_path / "bad.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="at least 3 vertices"):
            load_geometry(f)

    def test_vertex_outside_canvas(self, tmp_path: Path) -> None:
        """A vertex outside the canvas should raise ValueError."""
        # Arrange
        content = """\
canvas:
  size: 50
buildings:
  - name: big
    vertices:
      - [0, 0]
      - [51, 0]
      - [51, 51]
"""
        f = tmp_path / "out.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="outside canvas bounds"):
            load_geometry(f)

    def test_highlighted_region_vertex_outside_canvas(self, tmp_path: Path) -> None:
        """A highlighted region vertex beyond canvas should raise ValueError."""
        # Arrange
        content = """\
canvas:
  size: 100
buildings:
  - name: ok
    vertices:
      - [0, 0]
      - [10, 0]
      - [10, 10]
highlighted_regions:
  - name: overflow
    vertices:
      - [90, 90]
      - [110, 90]
      - [110, 110]
    color: red
"""
        f = tmp_path / "region.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="outside canvas bounds"):
            load_geometry(f)

    def test_highlighted_region_fewer_than_three_vertices(self, tmp_path: Path) -> None:
        """A highlighted region with fewer than 3 vertices should raise ValueError."""
        # Arrange
        content = """\
buildings:
  - name: ok
    vertices:
      - [0, 0]
      - [10, 0]
      - [10, 10]
highlighted_regions:
  - name: tiny
    vertices:
      - [0, 0]
      - [5, 5]
    color: blue
"""
        f = tmp_path / "region_small.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="at least 3 vertices"):
            load_geometry(f)

    def test_error_message_includes_building_name(self, tmp_path: Path) -> None:
        """Validation errors should include the offending shape name."""
        # Arrange
        content = """\
buildings:
  - name: problematic_tower
    vertices:
      - [0, 0]
      - [200, 0]
      - [200, 200]
"""
        f = tmp_path / "named.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="problematic_tower"):
            load_geometry(f)

    def test_validation_error_raised_as_value_error(self, tmp_path: Path) -> None:
        """Pydantic ValidationError should be wrapped as ValueError."""
        # Arrange
        f = tmp_path / "bad.yaml"
        f.write_text("buildings: not_a_list\n")

        # Act / Assert
        with pytest.raises(ValueError):
            load_geometry(f)


# ---------------------------------------------------------------------------
# Vertex boundary values
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVertexBoundaryValues:
    """Boundary value analysis: vertices at exact canvas edges."""

    def test_vertex_at_origin(self, tmp_path: Path) -> None:
        """Vertex at (0, 0) should be valid."""
        # Arrange
        content = """\
buildings:
  - name: corner
    vertices:
      - [0, 0]
      - [10, 0]
      - [10, 10]
"""
        f = tmp_path / "origin.yaml"
        f.write_text(content)

        # Act
        config = load_geometry(f)

        # Assert
        assert config.buildings[0].vertices[0] == (0, 0)

    def test_vertex_at_max_corner(self, tmp_path: Path) -> None:
        """Vertex at (size, size) should be valid (inclusive upper bound)."""
        # Arrange
        content = """\
canvas:
  size: 50
buildings:
  - name: edge
    vertices:
      - [0, 0]
      - [50, 0]
      - [50, 50]
"""
        f = tmp_path / "max.yaml"
        f.write_text(content)

        # Act
        config = load_geometry(f)

        # Assert
        assert config.buildings[0].vertices[2] == (50, 50)

    def test_float_vertex_at_boundary(self, tmp_path: Path) -> None:
        """Float vertex at exactly canvas size should be valid."""
        # Arrange
        content = """\
canvas:
  size: 50
buildings:
  - name: precise
    vertices:
      - [0.0, 0.0]
      - [50.0, 0.0]
      - [50.0, 50.0]
"""
        f = tmp_path / "float_boundary.yaml"
        f.write_text(content)

        # Act
        config = load_geometry(f)

        # Assert
        assert config.buildings[0].vertices[2] == (50.0, 50.0)

    def test_vertex_one_past_max_is_invalid(self, tmp_path: Path) -> None:
        """Vertex at (size+1, 0) should fail validation."""
        # Arrange
        content = """\
canvas:
  size: 50
buildings:
  - name: oob
    vertices:
      - [0, 0]
      - [51, 0]
      - [51, 10]
"""
        f = tmp_path / "past.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="outside canvas bounds"):
            load_geometry(f)

    def test_negative_vertex_is_invalid(self, tmp_path: Path) -> None:
        """Vertex with a negative coordinate should fail validation."""
        # Arrange
        content = """\
buildings:
  - name: neg
    vertices:
      - [-1, 0]
      - [10, 0]
      - [10, 10]
"""
        f = tmp_path / "neg.yaml"
        f.write_text(content)

        # Act / Assert
        with pytest.raises(ValueError, match="outside canvas bounds"):
            load_geometry(f)


# ---------------------------------------------------------------------------
# fit_to_circle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFitToCircle:
    """Tests for auto-scaling geometry to fit within the canvas circle."""

    def test_vertices_already_inside_returns_unchanged(self) -> None:
        """When all vertices fit within the circle, geometry is returned as-is."""
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="a",
                    vertices=[(45, 45), (55, 45), (55, 55), (45, 55)],
                ),
            ],
        )

        result = fit_to_circle(geometry)

        assert result is geometry

    def test_vertices_on_boundary_with_no_padding_unchanged(self) -> None:
        """Vertices exactly on the circle boundary with no padding are not scaled."""
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="a",
                    vertices=[(0, 50), (100, 50), (50, 0), (50, 100)],
                ),
            ],
        )

        result = fit_to_circle(geometry, padding_fraction=0.0)

        assert result is geometry

    def test_vertices_outside_circle_are_scaled_in(self) -> None:
        """Corner vertices exceed the circle and are scaled inward."""
        # Arrange — corners at distance hypot(50,50)≈70.7 from center
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="a",
                    vertices=[(0, 0), (100, 0), (100, 100), (0, 100)],
                ),
            ],
        )

        # Act
        result = fit_to_circle(geometry, padding_fraction=0.0)

        # Assert — every vertex is now within the circle
        import math

        for x, y in result.buildings[0].vertices:
            dist = math.hypot(x - 50, y - 50)
            assert dist <= 50.0 + 1e-10

    def test_padding_shrinks_further(self) -> None:
        """With padding, vertices on the boundary are scaled inward."""
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="a",
                    vertices=[(0, 50), (100, 50), (50, 0), (50, 100)],
                ),
            ],
        )

        result = fit_to_circle(geometry, padding_fraction=0.10)

        # Original max distance = 50, fit_radius = 50*(1-0.1) = 45, scale = 0.9
        v = result.buildings[0].vertices
        assert v[0][0] == pytest.approx(5.0, abs=1e-10)
        assert v[1][0] == pytest.approx(95.0, abs=1e-10)

    def test_highlighted_regions_also_scaled(self) -> None:
        """Highlighted regions are scaled along with buildings."""
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(name="a", vertices=[(0, 50), (100, 50), (50, 0)]),
            ],
            highlighted_regions=[
                HighlightedRegion(
                    name="r",
                    vertices=[(40, 40), (60, 40), (60, 60)],
                    color="#ff0",
                ),
            ],
        )

        result = fit_to_circle(geometry, padding_fraction=0.10)

        rv = result.highlighted_regions[0].vertices
        assert rv[0][0] == pytest.approx(50 + (40 - 50) * 0.9, abs=1e-10)
        assert rv[0][1] == pytest.approx(50 + (40 - 50) * 0.9, abs=1e-10)

    def test_uniform_scaling_preserves_shape(self) -> None:
        """Scaling is uniform — relative proportions between vertices are preserved."""
        # Arrange — corners at ~70.7 from center, triggers scaling
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="a",
                    vertices=[(0, 0), (100, 0), (50, 100)],
                ),
            ],
        )
        orig = geometry.buildings[0].vertices

        # Act
        result = fit_to_circle(geometry, padding_fraction=0.10)

        # Assert — width/height ratio preserved
        scaled = result.buildings[0].vertices
        orig_width = orig[1][0] - orig[0][0]
        scaled_width = scaled[1][0] - scaled[0][0]
        orig_height = orig[2][1] - orig[0][1]
        scaled_height = scaled[2][1] - scaled[0][1]
        assert (scaled_width / scaled_height) == pytest.approx(
            orig_width / orig_height, abs=1e-10
        )

    def test_no_displacement_returns_unchanged(self) -> None:
        """Vertices all at center have max_dist=0, so geometry is returned as-is."""
        geometry = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(name="a", vertices=[(50, 50), (50, 50), (50, 50)]),
            ],
        )

        result = fit_to_circle(geometry)

        assert result is geometry
