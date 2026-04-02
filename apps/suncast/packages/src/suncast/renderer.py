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


@dataclass(frozen=True, slots=True)
class RenderSettings:
    """Visual settings for the SVG renderer."""

    primary_color: str = "#614c1f"
    secondary_color: str = "#b38c3a"
    light_color: str = "#f1b023"
    shadow_color: str = "#0A0A0A"
    stroke_width: float = 1.0


def points_to_path(points: tuple[Point, ...]) -> str:
    """Convert a sequence of points to an SVG path ``d`` attribute."""
    if not points:
        return ""
    parts = [f"M{points[0].x:.2f},{points[0].y:.2f}"]
    parts.extend(f"L{p.x:.2f},{p.y:.2f}" for p in points[1:])
    parts.append("Z")
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
        s = settings or RenderSettings()
        canvas = geometry.canvas.size
        margin = 20
        total = canvas + 2 * margin
        cx, cy = canvas / 2, canvas / 2
        radius = canvas / 2

        parts: list[str] = []

        # 1. SVG root
        parts.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{-margin} {-margin} {total} {total}">'
        )

        # 2. Defs: circular clip mask
        parts.append("<defs>")
        parts.append('<mask id="circle-mask">')
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="white"/>')
        parts.append("</mask>")
        parts.append("</defs>")

        # 3. Shadow polygons (daylight only)
        if sun.is_daylight and shadows:
            parts.append('<g class="shadows" mask="url(#circle-mask)">')
            for sr in shadows:
                d = points_to_path(sr.shadow_polygon)
                parts.append(f'<path d="{d}" fill="{s.shadow_color}"/>')
            parts.append("</g>")

        # 4 & 5. Building outlines and home fill
        parts.append('<g class="buildings">')
        for b in geometry.buildings:
            pts = tuple(Point(x, y) for x, y in b.vertices)
            d = points_to_path(pts)
            stroke = s.secondary_color if b.style == "home" else s.primary_color
            fill_attr = s.secondary_color if b.style == "home" else "none"
            parts.append(
                f'<path d="{d}" stroke="{stroke}" '
                f'stroke-width="{s.stroke_width}" fill="{fill_attr}"/>'
            )
        parts.append("</g>")

        # 6. Highlighted regions
        if geometry.highlighted_regions:
            parts.append('<g class="highlights">')
            for hr in geometry.highlighted_regions:
                pts = tuple(Point(x, y) for x, y in hr.vertices)
                d = points_to_path(pts)
                parts.append(f'<path d="{d}" fill="{hr.color}" opacity="0.5"/>')
            parts.append("</g>")

        # 7. Illuminated edge highlight
        if sun.is_daylight:
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
                f'fill="none" stroke="{s.light_color}" '
                f'stroke-width="{s.stroke_width}" class="illuminated-edge"/>'
            )

        # 8. Day/night arc
        north_rot = geometry.canvas.north_rotation
        if sun.sunrise_azimuth is not None and sun.sunset_azimuth is not None:
            day_d = arc_path(
                Point(cx, cy),
                radius,
                apply_north_rotation(sun.sunrise_azimuth, north_rot),
                apply_north_rotation(sun.sunset_azimuth, north_rot),
            )
            night_d = arc_path(
                Point(cx, cy),
                radius,
                apply_north_rotation(sun.sunset_azimuth, north_rot),
                apply_north_rotation(sun.sunrise_azimuth, north_rot),
            )
            parts.append(
                f'<path d="{day_d}" fill="none" stroke="{s.light_color}" '
                f'stroke-width="{s.stroke_width * 2}" class="day-arc"/>'
            )
            parts.append(
                f'<path d="{night_d}" fill="none" stroke="{s.primary_color}" '
                f'stroke-width="{s.stroke_width * 2}" class="night-arc"/>'
            )

        # 9. Sundial (hourly azimuth lines)
        parts.append('<g class="sundial">')
        for i, az in enumerate(sun.hourly_azimuths):
            adjusted = apply_north_rotation(az, north_rot)
            end = degrees_to_cartesian(adjusted, radius, Point(cx, cy))
            opacity = 0.6 if i % 2 == 0 else 0.3
            parts.append(
                f'<line x1="{cx}" y1="{cy}" x2="{end.x:.2f}" y2="{end.y:.2f}" '
                f'stroke="{s.primary_color}" stroke-width="0.5" '
                f'opacity="{opacity}" class="sundial-line"/>'
            )
        # Sunrise/sunset indicators
        if sun.sunrise_azimuth is not None:
            sr_pt = degrees_to_cartesian(
                apply_north_rotation(sun.sunrise_azimuth, north_rot),
                radius,
                Point(cx, cy),
            )
            parts.append(
                f'<circle cx="{sr_pt.x:.2f}" cy="{sr_pt.y:.2f}" r="3" '
                f'fill="{s.light_color}" class="sunrise-marker"/>'
            )
        if sun.sunset_azimuth is not None:
            ss_pt = degrees_to_cartesian(
                apply_north_rotation(sun.sunset_azimuth, north_rot),
                radius,
                Point(cx, cy),
            )
            parts.append(
                f'<circle cx="{ss_pt.x:.2f}" cy="{ss_pt.y:.2f}" r="3" '
                f'fill="{s.primary_color}" class="sunset-marker"/>'
            )
        parts.append("</g>")

        # 10. Sun position marker
        sun_adj = apply_north_rotation(sun.azimuth, north_rot)
        sun_pt = degrees_to_cartesian(sun_adj, radius, Point(cx, cy))
        parts.append(
            f'<circle cx="{sun_pt.x:.2f}" cy="{sun_pt.y:.2f}" r="5" '
            f'fill="{s.light_color}" stroke="{s.primary_color}" '
            f'stroke-width="1" class="sun-marker"/>'
        )

        parts.append("</svg>")
        return "\n".join(parts)
