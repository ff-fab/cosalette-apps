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

"""Shadow projection geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

from suncast.domain.geometry import GeometryConfig
from suncast.domain.solar import SunPosition


class Point(NamedTuple):
    """2D point on the canvas."""

    x: float
    y: float


type Polygon = list[Point]


@dataclass(frozen=True, slots=True)
class ShadowResult:
    """Shadow projection result for a single building."""

    building_name: str
    shadow_polygon: Polygon


def degrees_to_cartesian(azimuth_deg: float, distance: float, center: Point) -> Point:
    """Convert compass azimuth and distance to canvas coordinates."""
    azimuth_rad = math.radians(azimuth_deg)
    x = center.x + distance * math.sin(azimuth_rad)
    y = center.y - distance * math.cos(azimuth_rad)
    return Point(x, y)


def apply_north_rotation(azimuth: float, north_rotation: float) -> float:
    """Adjust azimuth by the canvas north rotation offset (ADR-003)."""
    return (azimuth - north_rotation) % 360


def compute_shadow_polygon(
    vertices: list[tuple[float, float]],
    sun_azimuth: float,
    sun_elevation: float,
    canvas_size: int,
) -> Polygon:
    """Compute the shadow polygon for a building footprint."""
    if sun_elevation <= 0 or sun_elevation >= 90:
        return []
    if len(vertices) < 3:
        return []

    shadow_azimuth = (sun_azimuth + 180) % 360
    shadow_length = (1.0 / math.tan(math.radians(sun_elevation))) * canvas_size * 0.5

    base_points = [Point(vx, vy) for vx, vy in vertices]
    projected = [
        degrees_to_cartesian(shadow_azimuth, shadow_length, Point(vx, vy))
        for vx, vy in vertices
    ]

    return base_points + list(reversed(projected))


def clip_to_circle(polygon: Polygon, center: Point, radius: float) -> Polygon:
    """Clamp polygon points that exceed the circle boundary."""
    if not polygon:
        return []
    result: Polygon = []
    for p in polygon:
        dx = p.x - center.x
        dy = p.y - center.y
        dist = math.hypot(dx, dy)
        if dist > radius:
            scale = radius / dist
            result.append(Point(center.x + dx * scale, center.y + dy * scale))
        else:
            result.append(p)
    return result


def compute_building_shadows(
    geometry: GeometryConfig, sun: SunPosition
) -> list[ShadowResult]:
    """Compute shadow projections for all buildings in the geometry."""
    if sun.elevation <= 0:
        return []

    adjusted_azimuth = apply_north_rotation(sun.azimuth, geometry.canvas.north_rotation)
    center = Point(geometry.canvas.size / 2, geometry.canvas.size / 2)
    radius = geometry.canvas.size / 2

    results: list[ShadowResult] = []
    for building in geometry.buildings:
        if not building.casts_shadow:
            continue
        shadow = compute_shadow_polygon(
            building.vertices, adjusted_azimuth, sun.elevation, geometry.canvas.size
        )
        shadow = clip_to_circle(shadow, center, radius)
        if shadow:
            results.append(
                ShadowResult(building_name=building.name, shadow_polygon=shadow)
            )
    return results
