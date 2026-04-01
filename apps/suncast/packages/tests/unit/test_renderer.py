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

"""Unit tests for renderer.py — SVG shadow visualization rendering.

Test Techniques Used:
- Specification-based: SVG layer structure and element presence
- Equivalence Partitioning: Daylight vs nighttime rendering paths
- Condition Coverage: Building styles, highlighted regions, empty shadows
- Round-trip Testing: Valid XML output verification
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from suncast.domain.geometry import (
    BuildingConfig,
    CanvasConfig,
    GeometryConfig,
    HighlightedRegion,
)
from suncast.domain.shadow import Point, ShadowResult
from suncast.domain.solar import SunPosition
from suncast.renderer import RenderSettings, ShadowRenderer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def renderer() -> ShadowRenderer:
    """A default renderer instance."""
    return ShadowRenderer()


@pytest.fixture()
def settings() -> RenderSettings:
    """Default render settings."""
    return RenderSettings()


@pytest.fixture()
def geometry() -> GeometryConfig:
    """Geometry with a home and a neighbor building."""
    return GeometryConfig(
        canvas=CanvasConfig(size=100, north_rotation=0.0),
        buildings=[
            BuildingConfig(
                name="house",
                vertices=[(40, 40), (60, 40), (60, 60), (40, 60)],
                casts_shadow=True,
                style="home",
            ),
            BuildingConfig(
                name="garage",
                vertices=[(10, 10), (20, 10), (20, 20)],
                casts_shadow=True,
                style="neighbor",
            ),
        ],
    )


@pytest.fixture()
def daylight_sun() -> SunPosition:
    """Mid-day sun position."""
    return SunPosition(
        azimuth=180.0,
        elevation=45.0,
        sunrise_azimuth=90.0,
        sunset_azimuth=270.0,
        sunrise_time=None,
        sunset_time=None,
        hourly_azimuths=tuple(float(i * 15) for i in range(24)),
        is_daylight=True,
    )


@pytest.fixture()
def night_sun() -> SunPosition:
    """Night-time sun position (below horizon)."""
    return SunPosition(
        azimuth=0.0,
        elevation=-10.0,
        sunrise_azimuth=90.0,
        sunset_azimuth=270.0,
        sunrise_time=None,
        sunset_time=None,
        hourly_azimuths=tuple(float(i * 15) for i in range(24)),
        is_daylight=False,
    )


@pytest.fixture()
def shadow_results() -> list[ShadowResult]:
    """Sample shadow result for the house."""
    return [
        ShadowResult(
            building_name="house",
            shadow_polygon=(
                Point(40, 40),
                Point(60, 40),
                Point(60, 60),
                Point(40, 60),
                Point(40, 10),
                Point(60, 10),
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShadowRenderer:
    """Specification-based: SVG layer structure and rendering behavior."""

    def test_daytime_render_contains_required_layers(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        shadow_results: list[ShadowResult],
        geometry: GeometryConfig,
    ) -> None:
        """Daytime SVG contains shadow polygons, buildings, sundial, sun marker."""
        # Act
        svg = renderer.render(daylight_sun, shadow_results, geometry)

        # Assert
        assert 'class="shadows"' in svg
        assert 'class="buildings"' in svg
        assert 'class="sundial"' in svg
        assert 'class="sun-marker"' in svg

    def test_nighttime_render_no_shadow_polygons(
        self,
        renderer: ShadowRenderer,
        night_sun: SunPosition,
        geometry: GeometryConfig,
    ) -> None:
        """Nighttime SVG has no shadow polygons but still has sundial and sun marker."""
        # Act
        svg = renderer.render(night_sun, [], geometry)

        # Assert
        assert 'class="shadows"' not in svg
        assert 'class="sundial"' in svg
        assert 'class="sun-marker"' in svg

    def test_building_styles_home_vs_neighbor(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
        settings: RenderSettings,
    ) -> None:
        """Home buildings get secondary_color fill; neighbors get primary_color stroke.

        Technique: Condition Coverage — building style branching.
        """
        # Act
        svg = renderer.render(daylight_sun, [], geometry, settings)

        # Assert — home gets secondary fill, neighbor gets primary stroke
        assert f'fill="{settings.secondary_color}"' in svg
        assert f'stroke="{settings.primary_color}"' in svg

    def test_highlighted_regions_rendered(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
    ) -> None:
        """Highlighted regions appear with their configured colors.

        Technique: Specification-based — highlighted region rendering.
        """
        # Arrange
        geo = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="b", vertices=[(10, 10), (20, 10), (20, 20)], style="default"
                ),
            ],
            highlighted_regions=[
                HighlightedRegion(
                    name="patio",
                    vertices=[(30, 30), (40, 30), (40, 40)],
                    color="#0f0",
                ),
            ],
        )

        # Act
        svg = renderer.render(daylight_sun, [], geo)

        # Assert
        assert 'class="highlights"' in svg
        assert 'fill="#0f0"' in svg

    def test_day_night_arc_colors(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
        settings: RenderSettings,
    ) -> None:
        """Day arc uses light_color; night arc uses primary_color.

        Technique: Condition Coverage — arc color assignment.
        """
        # Act
        svg = renderer.render(daylight_sun, [], geometry, settings)

        # Assert
        assert f'stroke="{settings.light_color}"' in svg
        assert 'class="day-arc"' in svg
        assert 'class="night-arc"' in svg

    def test_sundial_has_24_hourly_lines(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
    ) -> None:
        """Sundial contains 24 hourly radial lines.

        Technique: Specification-based — sundial completeness.
        """
        # Act
        svg = renderer.render(daylight_sun, [], geometry)

        # Assert
        assert svg.count('class="sundial-line"') == 24

    def test_sun_position_marker_present(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
    ) -> None:
        """Sun position marker circle element exists in output.

        Technique: Specification-based — sun marker presence.
        """
        # Act
        svg = renderer.render(daylight_sun, [], geometry)

        # Assert
        assert 'class="sun-marker"' in svg
        # Marker is a circle element
        root = ET.fromstring(svg)
        markers = root.findall(
            ".//{http://www.w3.org/2000/svg}circle[@class='sun-marker']"
        )
        # Fallback for no-namespace parsing
        if not markers:
            markers = root.findall(".//*[@class='sun-marker']")
        assert len(markers) == 1

    def test_circular_mask_present(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
    ) -> None:
        """SVG contains a mask element with a circle for clipping.

        Technique: Specification-based — clip mask structure.
        """
        # Act
        svg = renderer.render(daylight_sun, [], geometry)

        # Assert
        assert '<mask id="circle-mask">' in svg
        assert "circle" in svg

    def test_valid_xml_output(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        shadow_results: list[ShadowResult],
        geometry: GeometryConfig,
    ) -> None:
        """Output parses as valid XML.

        Technique: Round-trip Testing — SVG structural validity.
        """
        # Act
        svg = renderer.render(daylight_sun, shadow_results, geometry)

        # Assert — should not raise
        root = ET.fromstring(svg)
        assert root.tag == "{http://www.w3.org/2000/svg}svg" or root.tag == "svg"

    def test_north_rotation_applied_to_arc(
        self,
        renderer: ShadowRenderer,
        settings: RenderSettings,
    ) -> None:
        """Day/night arc respects canvas north_rotation offset.

        Technique: Condition Coverage — north_rotation arc alignment.
        """
        # Arrange — same sun, two geometries differing only in north_rotation
        buildings = [
            BuildingConfig(
                name="b",
                vertices=[(10, 10), (20, 10), (20, 20)],
                style="default",
            ),
        ]
        geo_0 = GeometryConfig(
            canvas=CanvasConfig(size=100, north_rotation=0.0),
            buildings=buildings,
        )
        geo_90 = GeometryConfig(
            canvas=CanvasConfig(size=100, north_rotation=90.0),
            buildings=buildings,
        )
        sun = SunPosition(
            azimuth=180.0,
            elevation=45.0,
            sunrise_azimuth=90.0,
            sunset_azimuth=270.0,
            sunrise_time=None,
            sunset_time=None,
            hourly_azimuths=tuple(float(i * 15) for i in range(24)),
            is_daylight=True,
        )

        # Act
        svg_0 = renderer.render(sun, [], geo_0, settings)
        svg_90 = renderer.render(sun, [], geo_90, settings)

        # Assert — arc paths must differ when rotation differs
        assert 'class="day-arc"' in svg_0
        assert 'class="day-arc"' in svg_90
        assert svg_0 != svg_90

    def test_empty_shadows_list_no_shadow_group(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
    ) -> None:
        """Empty shadows list produces no shadow polygon group in the SVG.

        Technique: Condition Coverage — casts_shadow=False path.
        """
        # Arrange
        geo = GeometryConfig(
            canvas=CanvasConfig(size=100),
            buildings=[
                BuildingConfig(
                    name="decoy",
                    vertices=[(10, 10), (20, 10), (20, 20)],
                    casts_shadow=False,
                    style="default",
                ),
            ],
        )

        # Act
        svg = renderer.render(daylight_sun, [], geo)

        # Assert
        assert 'class="shadows"' not in svg

    def test_custom_colors_in_output(
        self,
        renderer: ShadowRenderer,
        daylight_sun: SunPosition,
        geometry: GeometryConfig,
    ) -> None:
        """Custom RenderSettings colors appear in the SVG output.

        Technique: Specification-based — settings propagation.
        """
        # Arrange
        custom = RenderSettings(
            primary_color="#111",
            secondary_color="#222",
            light_color="#333",
            shadow_color="#444",
        )

        # Act
        svg = renderer.render(daylight_sun, [], geometry, custom)

        # Assert
        assert "#111" in svg
        assert "#222" in svg
        assert "#333" in svg
