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

"""Unit tests for domain/geometry_svg.py — SVG geometry importer.

Test Techniques Used:
- Specification-based Testing: Verifying load_svg_geometry contracts and shape extraction
- Equivalence Partitioning: polygon elements, path elements, mixed elements
- Boundary Value Analysis: Minimum 3 vertices, viewBox coordinate transformation
- Error Guessing: Curve commands in paths, missing SVG file, no usable shapes
- Decision Table: Sidecar role mapping (building vs highlighted, with/without sidecar)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from suncast.domain.geometry_svg import load_svg_geometry

# ---------------------------------------------------------------------------
# SVG test data
# ---------------------------------------------------------------------------

SVG_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'

SVG_WITH_POLYGON = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon id="house" points="10,10 50,10 50,50 10,50" />
</svg>
"""

SVG_WITH_PATH_ABSOLUTE = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="shed" d="M 10,10 L 40,10 L 40,30 L 10,30 Z" />
</svg>
"""

SVG_WITH_PATH_RELATIVE = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="garage" d="M 5,5 l 20,0 l 0,15 l -20,0 z" />
</svg>
"""

SVG_WITH_HV_COMMANDS = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="box" d="M 10,10 H 40 V 30 H 10 Z" />
</svg>
"""

SVG_WITH_RELATIVE_HV = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="rbox" d="M 10,10 h 30 v 20 h -30 z" />
</svg>
"""

SVG_WITH_CURVE = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="curvy" d="M 10,10 C 20,20 40,20 50,10 L 50,50 L 10,50 Z" />
</svg>
"""

SVG_POLYGON_AND_CURVE = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon id="good" points="10,10 50,10 50,50 10,50" />
  <path id="bad" d="M 0,0 C 10,10 20,10 30,0 L 30,30 L 0,30 Z" />
</svg>
"""

SVG_NO_ID = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon points="10,10 50,10 50,50 10,50" />
  <polygon points="60,60 90,60 90,90 60,90" />
</svg>
"""

SVG_INKSCAPE_LABEL = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="100" height="100">
  <polygon inkscape:label="my_building" points="10,10 50,10 50,50 10,50" />
</svg>
"""

SVG_DATA_NAME = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon data-name="data_house" points="10,10 50,10 50,50 10,50" />
</svg>
"""

SVG_NAME_PRIORITY = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="100" height="100">
  <polygon id="id_wins" inkscape:label="label_loses" data-name="data_loses"
           points="10,10 50,10 50,50 10,50" />
</svg>
"""

SVG_WITH_VIEWBOX = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
  <polygon id="house" points="0,0 100,0 100,100 0,100" />
</svg>
"""

SVG_WITH_VIEWBOX_OFFSET = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" viewBox="100 100 200 200">
  <polygon id="house" points="100,100 200,100 200,200 100,200" />
</svg>
"""

SVG_EMPTY = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
</svg>
"""

SVG_ONLY_CURVES = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <path id="arc" d="M 10,10 A 20,20 0 0,1 50,50 Z" />
</svg>
"""

SVG_TOO_FEW_VERTICES = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon id="line" points="10,10 50,10" />
</svg>
"""

SVG_MULTIPLE_POLYGONS = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon id="building_a" points="10,10 40,10 40,40 10,40" />
  <polygon id="building_b" points="50,50 80,50 80,80 50,80" />
</svg>
"""

SIDECAR_WITH_ROLES = """\
canvas:
  north_rotation: 15.0

shape_roles:
  house:
    casts_shadow: true
    style: home
  garden:
    highlighted: true
    color: '#00ff00'
"""

SIDECAR_WITH_CANVAS_SIZE = """\
canvas:
  size: 50
  north_rotation: 10.0

shape_roles:
  house:
    style: neighbor
"""

SVG_TWO_SHAPES_FOR_SIDECAR = f"""{SVG_HEADER}
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <polygon id="house" points="10,10 50,10 50,50 10,50" />
  <polygon id="garden" points="60,60 90,60 90,90 60,90" />
</svg>
"""


# ---------------------------------------------------------------------------
# Polygon extraction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadSvgPolygon:
    """Specification-based: SVG <polygon> elements are correctly parsed."""

    def test_polygon_with_id(self, tmp_path: Path) -> None:
        """A polygon with an id attribute should be extracted by name."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_WITH_POLYGON)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "house"
        assert len(config.buildings[0].vertices) == 4
        assert config.buildings[0].vertices[0] == (10.0, 10.0)
        assert config.buildings[0].vertices[2] == (50.0, 50.0)

    def test_multiple_polygons(self, tmp_path: Path) -> None:
        """Multiple polygons should all be extracted."""
        # Arrange
        svg = tmp_path / "multi.svg"
        svg.write_text(SVG_MULTIPLE_POLYGONS)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 2
        names = {b.name for b in config.buildings}
        assert names == {"building_a", "building_b"}

    def test_polygon_defaults(self, tmp_path: Path) -> None:
        """Without sidecar, buildings get default properties."""
        # Arrange
        svg = tmp_path / "defaults.svg"
        svg.write_text(SVG_WITH_POLYGON)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.buildings[0].casts_shadow is True
        assert config.buildings[0].style == "default"


# ---------------------------------------------------------------------------
# Path extraction (straight lines)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadSvgPath:
    """Specification-based: SVG <path> elements with straight-line commands."""

    def test_path_absolute_lineto(self, tmp_path: Path) -> None:
        """Path with M/L/Z absolute commands should produce vertices."""
        # Arrange
        svg = tmp_path / "abs.svg"
        svg.write_text(SVG_WITH_PATH_ABSOLUTE)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "shed"
        assert len(config.buildings[0].vertices) >= 4

    def test_path_relative_lineto(self, tmp_path: Path) -> None:
        """Path with m/l/z relative commands should produce vertices."""
        # Arrange
        svg = tmp_path / "rel.svg"
        svg.write_text(SVG_WITH_PATH_RELATIVE)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "garage"
        verts = config.buildings[0].vertices
        # First vertex at (5, 5), last at (5, 20) given relative offsets.
        assert verts[0] == (5.0, 5.0)

    def test_path_hv_absolute(self, tmp_path: Path) -> None:
        """Path with H/V absolute commands should produce correct vertices."""
        # Arrange
        svg = tmp_path / "hv.svg"
        svg.write_text(SVG_WITH_HV_COMMANDS)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        verts = config.buildings[0].vertices
        # M 10,10 -> H 40 -> V 30 -> H 10
        assert verts[0] == (10.0, 10.0)
        assert verts[1] == (40.0, 10.0)
        assert verts[2] == (40.0, 30.0)
        assert verts[3] == (10.0, 30.0)

    def test_path_hv_relative(self, tmp_path: Path) -> None:
        """Path with h/v relative commands should produce correct vertices."""
        # Arrange
        svg = tmp_path / "hv_rel.svg"
        svg.write_text(SVG_WITH_RELATIVE_HV)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        verts = config.buildings[0].vertices
        # M 10,10 -> h 30 -> v 20 -> h -30
        assert verts[0] == (10.0, 10.0)
        assert verts[1] == (40.0, 10.0)
        assert verts[2] == (40.0, 30.0)
        assert verts[3] == (10.0, 30.0)


# ---------------------------------------------------------------------------
# Curve rejection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCurveRejection:
    """Error guessing: paths with curve commands are skipped with a warning."""

    def test_curve_path_skipped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A path with cubic bezier commands should be skipped entirely."""
        # Arrange
        svg = tmp_path / "curve.svg"
        svg.write_text(SVG_ONLY_CURVES)

        # Act / Assert
        with pytest.raises(ValueError, match="no usable building shapes"):
            with caplog.at_level(logging.WARNING):
                load_svg_geometry(svg)

    def test_curve_path_logs_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The warning should mention the skipped element name."""
        # Arrange
        svg = tmp_path / "mixed.svg"
        svg.write_text(SVG_POLYGON_AND_CURVE)

        # Act
        with caplog.at_level(logging.WARNING):
            config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].name == "good"
        assert any("bad" in record.message for record in caplog.records)

    def test_only_curve_raises(self, tmp_path: Path) -> None:
        """SVG with only curve paths should raise ValueError."""
        # Arrange
        svg = tmp_path / "curves_only.svg"
        svg.write_text(SVG_WITH_CURVE)

        # Act / Assert
        with pytest.raises(ValueError, match="no usable building shapes"):
            load_svg_geometry(svg)


# ---------------------------------------------------------------------------
# Shape naming priority
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShapeNaming:
    """Decision table: shape name resolution priority."""

    def test_id_attribute_wins(self, tmp_path: Path) -> None:
        """id attribute takes priority over all others."""
        # Arrange
        svg = tmp_path / "priority.svg"
        svg.write_text(SVG_NAME_PRIORITY)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.buildings[0].name == "id_wins"

    def test_inkscape_label_used(self, tmp_path: Path) -> None:
        """inkscape:label is used when id is absent."""
        # Arrange
        svg = tmp_path / "label.svg"
        svg.write_text(SVG_INKSCAPE_LABEL)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.buildings[0].name == "my_building"

    def test_data_name_used(self, tmp_path: Path) -> None:
        """data-name is used when id and inkscape:label are absent."""
        # Arrange
        svg = tmp_path / "dataname.svg"
        svg.write_text(SVG_DATA_NAME)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.buildings[0].name == "data_house"

    def test_auto_generated_names(self, tmp_path: Path) -> None:
        """Shapes without any name attribute get auto-generated names."""
        # Arrange
        svg = tmp_path / "noname.svg"
        svg.write_text(SVG_NO_ID)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 2
        names = {b.name for b in config.buildings}
        assert "shape_1" in names
        assert "shape_2" in names


# ---------------------------------------------------------------------------
# ViewBox coordinate transformation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestViewBoxTransformation:
    """Boundary value analysis: viewBox coordinate normalization."""

    def test_viewbox_sets_canvas_size(self, tmp_path: Path) -> None:
        """Canvas size should be derived from viewBox dimensions."""
        # Arrange
        svg = tmp_path / "vb.svg"
        svg.write_text(SVG_WITH_VIEWBOX)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.canvas.size == 200

    def test_viewbox_transforms_coordinates(self, tmp_path: Path) -> None:
        """Vertices should be scaled from viewBox to canvas coordinates."""
        # Arrange
        svg = tmp_path / "vb.svg"
        svg.write_text(SVG_WITH_VIEWBOX)

        # Act
        config = load_svg_geometry(svg)

        # Assert — viewBox is 200x200, canvas is 200, so 1:1 scale
        verts = config.buildings[0].vertices
        assert verts[0] == (0.0, 0.0)
        assert verts[1] == (100.0, 0.0)

    def test_viewbox_with_offset(self, tmp_path: Path) -> None:
        """viewBox with non-zero min-x/min-y should shift coordinates."""
        # Arrange
        svg = tmp_path / "offset.svg"
        svg.write_text(SVG_WITH_VIEWBOX_OFFSET)

        # Act
        config = load_svg_geometry(svg)

        # Assert — viewBox "100 100 200 200", canvas=200
        # Vertex (100,100) becomes (0,0), (200,100) becomes (100,0)
        verts = config.buildings[0].vertices
        assert verts[0] == (0.0, 0.0)
        assert verts[1] == (100.0, 0.0)

    def test_width_height_fallback(self, tmp_path: Path) -> None:
        """Without viewBox, canvas size comes from width/height attributes."""
        # Arrange
        svg = tmp_path / "wh.svg"
        svg.write_text(SVG_WITH_POLYGON)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert config.canvas.size == 100


# ---------------------------------------------------------------------------
# Sidecar YAML mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSidecarMapping:
    """Decision table: sidecar maps shapes to building/highlighted roles."""

    def test_sidecar_assigns_building_role(self, tmp_path: Path) -> None:
        """Sidecar can assign style and casts_shadow to a building."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_TWO_SHAPES_FOR_SIDECAR)
        sidecar = tmp_path / "scene.yaml"
        sidecar.write_text(SIDECAR_WITH_ROLES)

        # Act
        config = load_svg_geometry(svg, sidecar)

        # Assert
        house = next(b for b in config.buildings if b.name == "house")
        assert house.casts_shadow is True
        assert house.style == "home"

    def test_sidecar_assigns_highlight_role(self, tmp_path: Path) -> None:
        """Sidecar with highlighted=true creates a HighlightedRegion."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_TWO_SHAPES_FOR_SIDECAR)
        sidecar = tmp_path / "scene.yaml"
        sidecar.write_text(SIDECAR_WITH_ROLES)

        # Act
        config = load_svg_geometry(svg, sidecar)

        # Assert
        assert len(config.highlighted_regions) == 1
        assert config.highlighted_regions[0].name == "garden"
        assert config.highlighted_regions[0].color == "#00ff00"

    def test_sidecar_north_rotation(self, tmp_path: Path) -> None:
        """Sidecar can set north_rotation on the canvas."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_TWO_SHAPES_FOR_SIDECAR)
        sidecar = tmp_path / "scene.yaml"
        sidecar.write_text(SIDECAR_WITH_ROLES)

        # Act
        config = load_svg_geometry(svg, sidecar)

        # Assert
        assert config.canvas.north_rotation == 15.0

    def test_sidecar_overrides_canvas_size(self, tmp_path: Path) -> None:
        """Sidecar canvas.size overrides SVG-derived size."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_WITH_POLYGON)
        sidecar = tmp_path / "scene.yaml"
        sidecar.write_text(SIDECAR_WITH_CANVAS_SIZE)

        # Act
        config = load_svg_geometry(svg, sidecar)

        # Assert
        assert config.canvas.size == 50

    def test_no_sidecar_defaults(self, tmp_path: Path) -> None:
        """Without sidecar, all shapes become buildings with defaults."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_MULTIPLE_POLYGONS)

        # Act
        config = load_svg_geometry(svg)

        # Assert
        assert len(config.buildings) == 2
        assert config.highlighted_regions == []
        for b in config.buildings:
            assert b.casts_shadow is True
            assert b.style == "default"

    def test_missing_sidecar_file(self, tmp_path: Path) -> None:
        """A sidecar path that doesn't exist should be treated as absent."""
        # Arrange
        svg = tmp_path / "scene.svg"
        svg.write_text(SVG_WITH_POLYGON)
        missing = tmp_path / "nonexistent.yaml"

        # Act
        config = load_svg_geometry(svg, missing)

        # Assert
        assert len(config.buildings) == 1
        assert config.buildings[0].casts_shadow is True


# ---------------------------------------------------------------------------
# Error conditions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestErrorConditions:
    """Error guessing: invalid inputs and edge cases."""

    def test_svg_file_not_found(self, tmp_path: Path) -> None:
        """Missing SVG file should raise FileNotFoundError."""
        # Arrange
        missing = tmp_path / "missing.svg"

        # Act / Assert
        with pytest.raises(FileNotFoundError):
            load_svg_geometry(missing)

    def test_empty_svg_raises(self, tmp_path: Path) -> None:
        """SVG with no polygon or path elements should raise ValueError."""
        # Arrange
        svg = tmp_path / "empty.svg"
        svg.write_text(SVG_EMPTY)

        # Act / Assert
        with pytest.raises(ValueError, match="no usable building shapes"):
            load_svg_geometry(svg)

    def test_too_few_vertices_skipped(self, tmp_path: Path) -> None:
        """Polygon with fewer than 3 vertices should be skipped."""
        # Arrange
        svg = tmp_path / "few.svg"
        svg.write_text(SVG_TOO_FEW_VERTICES)

        # Act / Assert
        with pytest.raises(ValueError, match="no usable building shapes"):
            load_svg_geometry(svg)
