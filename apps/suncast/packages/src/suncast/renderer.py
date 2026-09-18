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

# Inspired by the sun position and shadow visualization concept shared by
# pmpkk (Patrick) on the OpenHAB community forum:
# https://community.openhab.org/t/show-current-sun-position-and-shadow-of-house-generate-svg/34764

"""SVG shadow visualization renderer."""

from __future__ import annotations

from dataclasses import dataclass

from suncast.domain.geometry import GeometryConfig
from suncast.domain.shadow import (
    Point,
    ShadowResult,
    apply_north_rotation,
    degrees_to_cartesian,
)
from suncast.domain.solar import SunPosition
from suncast.settings import RenderStyle

# The renderer's visual value object lives with the settings it mirrors; see
# suncast.settings.RenderStyle. Re-exported here for the renderer's public API.
RenderSettings = RenderStyle


def points_to_path(points: tuple[Point, ...]) -> str:
    """Convert a sequence of points to an SVG path ``d`` attribute."""
    if not points:
        return ""
    parts = [f"M{points[0].x:.2f},{points[0].y:.2f}"]
    parts.extend(f"L{p.x:.2f},{p.y:.2f}" for p in points[1:])
    parts.append("Z")
    return "".join(parts)


def points_to_open_path(points: tuple[Point, ...]) -> str:
    """Convert points to an open SVG polyline path (no closing ``Z``)."""
    if not points:
        return ""
    parts = [f"M{points[0].x:.2f},{points[0].y:.2f}"]
    parts.extend(f"L{p.x:.2f},{p.y:.2f}" for p in points[1:])
    return "".join(parts)


def arc_path(center: Point, radius: float, start_deg: float, end_deg: float) -> str:
    """Build an SVG arc path from *start_deg* to *end_deg* (compass degrees)."""

    def _to_xy(deg: float) -> Point:
        return degrees_to_cartesian(deg, radius, center)

    start = _to_xy(start_deg)
    end = _to_xy(end_deg)
    sweep = (end_deg - start_deg) % 360
    large = 1 if sweep > 180 else 0
    return (
        f"M{start.x:.2f},{start.y:.2f}"
        f"A{radius:.2f},{radius:.2f} 0 {large},1 {end.x:.2f},{end.y:.2f}"
    )


@dataclass(frozen=True)
class _Frame:
    """The per-render values every SVG section derives its coordinates from."""

    sun: SunPosition
    style: RenderSettings
    cx: float
    cy: float
    radius: float
    north_rot: float

    @property
    def center(self) -> Point:
        return Point(self.cx, self.cy)

    def rotate(self, azimuth: float) -> float:
        """Apply the canvas' north rotation to a compass *azimuth*."""
        return apply_north_rotation(azimuth, self.north_rot)


def _sun_facing_section(frame: _Frame, shadows: list[ShadowResult]) -> list[str]:
    """Sun-facing edge outlines (rendered before shadows so shadows cover them)."""
    if not (frame.sun.is_daylight and shadows):
        return []
    s = frame.style
    parts = ['<g class="sun-facing">']
    for sr in shadows:
        if sr.sun_facing_edges:
            d = points_to_open_path(sr.sun_facing_edges)
            parts.append(
                f'<path d="{d}" stroke="{s.light_color}" '
                f'stroke-width="{s.stroke_width * 2}" fill="none" '
                f'class="sun-facing-edge"/>'
            )
    parts.append("</g>")
    return parts


def _shadows_section(frame: _Frame, shadows: list[ShadowResult]) -> list[str]:
    """Shadow polygons (daylight only)."""
    if not (frame.sun.is_daylight and shadows):
        return []
    parts = ['<g class="shadows" mask="url(#circle-mask)">']
    for sr in shadows:
        d = points_to_path(sr.shadow_polygon)
        parts.append(f'<path d="{d}" fill="{frame.style.shadow_color}"/>')
    parts.append("</g>")
    return parts


def _buildings_section(geometry: GeometryConfig, style: RenderSettings) -> list[str]:
    """Building outlines and home fill."""
    parts = ['<g class="buildings">']
    for b in geometry.buildings:
        pts = tuple(Point(x, y) for x, y in b.vertices)
        d = points_to_path(pts)
        fill_attr = style.secondary_color if b.style == "home" else style.primary_color
        parts.append(f'<path d="{d}" fill="{fill_attr}"/>')
    parts.append("</g>")
    return parts


def _highlights_section(geometry: GeometryConfig) -> list[str]:
    """Highlighted regions."""
    if not geometry.highlighted_regions:
        return []
    parts = ['<g class="highlights">']
    for hr in geometry.highlighted_regions:
        pts = tuple(Point(x, y) for x, y in hr.vertices)
        d = points_to_path(pts)
        parts.append(f'<path d="{d}" fill="{hr.color}" opacity="0.5"/>')
    parts.append("</g>")
    return parts


def _illuminated_edge_section(frame: _Frame) -> list[str]:
    """Illuminated edge highlight (suppressed in compact — hour arcs replace it)."""
    s = frame.style
    if not frame.sun.is_daylight or s.sundial_mode == "compact":
        return []
    edge_width = s.stroke_width * 2 / 3
    return [
        f'<circle cx="{frame.cx}" cy="{frame.cy}" r="{frame.radius}" '
        f'fill="none" stroke="{s.light_color}" '
        f'stroke-width="{edge_width:.2f}" class="illuminated-edge"/>'
    ]


def _day_night_paths(frame: _Frame) -> tuple[str | None, str | None]:
    """Day and night arc path data; ``(None, None)`` without sunrise/sunset."""
    sun = frame.sun
    if sun.sunrise_azimuth is None or sun.sunset_azimuth is None:
        return None, None
    sunrise = frame.rotate(sun.sunrise_azimuth)
    sunset = frame.rotate(sun.sunset_azimuth)
    day_d = arc_path(frame.center, frame.radius, sunrise, sunset)
    night_d = arc_path(frame.center, frame.radius, sunset, sunrise)
    return day_d, night_d


def _day_night_section(
    frame: _Frame, day_d: str | None, night_d: str | None
) -> list[str]:
    """Day/night arc (suppressed in compact mode)."""
    s = frame.style
    if day_d is None or night_d is None or s.sundial_mode == "compact":
        return []
    return [
        f'<path d="{day_d}" fill="none" stroke="{s.light_color}" '
        f'stroke-width="{s.stroke_width * 2}" class="day-arc"/>',
        f'<path d="{night_d}" fill="none" stroke="{s.primary_color}" '
        f'stroke-width="{s.stroke_width * 2}" class="night-arc"/>',
    ]


def _sundial_arcs(frame: _Frame, dial_radius: float) -> list[str]:
    """The 24 alternating hour arcs of the sundial."""
    hourly = frame.sun.hourly_azimuths
    parts: list[str] = []
    for i in range(24):
        d = arc_path(
            frame.center,
            dial_radius,
            frame.rotate(hourly[i]),
            frame.rotate(hourly[(i + 1) % 24]),
        )
        opacity = 0.2 if i % 2 == 0 else 1.0
        parts.append(
            f'<path d="{d}" stroke="{frame.style.primary_color}" '
            f'stroke-width="3" fill="none" '
            f'stroke-opacity="{opacity}" class="sundial-arc"/>'
        )
    return parts


def _hour_bar(
    frame: _Frame,
    hour_index: int,
    line_class: str,
    inner_radius: float,
    outer_radius: float,
) -> str:
    """A radial bar at the given hour, between *inner_radius* and *outer_radius*."""
    azimuth = frame.rotate(frame.sun.hourly_azimuths[hour_index])
    inner = degrees_to_cartesian(azimuth, inner_radius, frame.center)
    outer = degrees_to_cartesian(azimuth, outer_radius, frame.center)
    return (
        f'<line x1="{inner.x:.2f}" y1="{inner.y:.2f}" '
        f'x2="{outer.x:.2f}" y2="{outer.y:.2f}" '
        f'stroke="{frame.style.light_color}" stroke-width="2" '
        f'class="{line_class}"/>'
    )


def _sundial_ring_or_compact(frame: _Frame, day_d: str | None) -> list[str]:
    """Hour arcs plus the midnight and noon bars for ring/compact modes."""
    s = frame.style
    if s.sundial_mode not in {"ring", "compact"}:
        return []
    radius = frame.radius
    ring = s.sundial_mode == "ring"
    dial_radius = radius + 8 if ring else radius
    bar_inner_radius = radius + 4 if ring else radius - 4
    bar_outer_radius = radius + 12 if ring else radius + 4

    parts = _sundial_arcs(frame, dial_radius)
    if s.sundial_mode == "compact" and day_d is not None:
        parts.append(
            f'<path d="{day_d}" fill="none" stroke="{s.light_color}" '
            f'stroke-width="3" stroke-opacity="0.5" class="day-arc"/>'
        )
    bar_radii = (bar_inner_radius, bar_outer_radius)
    parts.append(_hour_bar(frame, 0, "midnight-bar", *bar_radii))
    parts.append(_hour_bar(frame, 12, "noon-bar", *bar_radii))
    return parts


def _horizon_marker(
    frame: _Frame, azimuth: float | None, color: str, css_class: str
) -> list[str]:
    """Sunrise/sunset indicator: a radial bar or a dot, per ``marker_style``."""
    if azimuth is None:
        return []
    az = frame.rotate(azimuth)
    if frame.style.marker_style == "bar":
        inner = degrees_to_cartesian(az, frame.radius - 5, frame.center)
        outer = degrees_to_cartesian(az, frame.radius + 5, frame.center)
        return [
            f'<line x1="{inner.x:.2f}" y1="{inner.y:.2f}" '
            f'x2="{outer.x:.2f}" y2="{outer.y:.2f}" '
            f'stroke="{color}" stroke-width="2" '
            f'class="{css_class}"/>'
        ]
    pt = degrees_to_cartesian(az, frame.radius, frame.center)
    return [
        f'<circle cx="{pt.x:.2f}" cy="{pt.y:.2f}" r="3" '
        f'fill="{color}" class="{css_class}"/>'
    ]


def _sundial_section(frame: _Frame, day_d: str | None) -> list[str]:
    """The sundial group: hour ring/arcs plus sunrise and sunset indicators."""
    s = frame.style
    sun = frame.sun
    return [
        '<g class="sundial">',
        *_sundial_ring_or_compact(frame, day_d),
        *_horizon_marker(frame, sun.sunrise_azimuth, s.light_color, "sunrise-marker"),
        *_horizon_marker(frame, sun.sunset_azimuth, s.primary_color, "sunset-marker"),
        "</g>",
    ]


def _sun_marker(frame: _Frame) -> str:
    """Sun position marker."""
    sun_pt = degrees_to_cartesian(
        frame.rotate(frame.sun.azimuth), frame.radius, frame.center
    )
    s = frame.style
    return (
        f'<circle cx="{sun_pt.x:.2f}" cy="{sun_pt.y:.2f}" r="4.5" '
        f'fill="{s.light_color}" stroke="{s.primary_color}" '
        f'stroke-width="1" class="sun-marker"/>'
    )


class ShadowRenderer:
    """Renders an SVG shadow visualization."""

    def render(
        self,
        sun: SunPosition,
        shadows: list[ShadowResult],
        geometry: GeometryConfig,
        settings: RenderSettings | None = None,
    ) -> str:
        """Return a complete SVG string."""
        style = settings or RenderSettings()
        canvas = geometry.canvas.size
        margin = 20
        total = canvas + 2 * margin
        frame = _Frame(
            sun=sun,
            style=style,
            cx=canvas / 2,
            cy=canvas / 2,
            radius=canvas / 2,
            north_rot=geometry.canvas.north_rotation,
        )
        day_d, night_d = _day_night_paths(frame)

        parts = [
            # 1. SVG root
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{-margin} {-margin} {total} {total}">',
            # 2. Defs: circular clip mask
            "<defs>",
            '<mask id="circle-mask">',
            f'<circle cx="{frame.cx}" cy="{frame.cy}" '
            f'r="{frame.radius}" fill="white"/>',
            "</mask>",
            "</defs>",
            *_sun_facing_section(frame, shadows),
            *_shadows_section(frame, shadows),
            *_buildings_section(geometry, style),
            *_highlights_section(geometry),
            *_illuminated_edge_section(frame),
            *_day_night_section(frame, day_d, night_d),
            *_sundial_section(frame, day_d),
            _sun_marker(frame),
            "</svg>",
        ]
        return "\n".join(parts)
