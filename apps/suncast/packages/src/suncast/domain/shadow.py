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


type Polygon = tuple[Point, ...]


@dataclass(frozen=True, slots=True)
class ShadowResult:
    """Shadow projection result for a single building."""

    building_name: str
    shadow_polygon: Polygon
    sun_facing_edges: Polygon


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
) -> tuple[Polygon, Polygon]:
    """Compute the shadow polygon for a building footprint via silhouette detection.

    Uses angle extrema from a distant sun reference point to identify the
    silhouette edges of the polygon. Projects the silhouette boundary vertices
    outward to form the shadow polygon.

    Returns a tuple of (shadow_polygon, sun_facing_edges).
    """
    empty: tuple[Polygon, Polygon] = ((), ())
    if sun_elevation <= 0 or sun_elevation >= 90:
        return empty
    if len(vertices) < 3:
        return empty

    pts = [Point(vx, vy) for vx, vy in vertices]
    n = len(pts)

    # 1. Project the sun to a distant reference point along the sun azimuth.
    centroid = Point(
        sum(p.x for p in pts) / n,
        sum(p.y for p in pts) / n,
    )
    sun_ref = degrees_to_cartesian(sun_azimuth, 10000.0, centroid)

    # 2. Compute angle from each vertex to the distant sun point.
    angles = [-math.degrees(math.atan2(p.y - sun_ref.y, p.x - sun_ref.x)) for p in pts]

    # 3. Find min-angle and max-angle vertex indices (silhouette extremes).
    min_idx = min(range(n), key=lambda i: angles[i])
    max_idx = max(range(n), key=lambda i: angles[i])

    # 4. Trace forward from min-angle vertex to max-angle vertex → side1 (sun-facing).
    side1: list[Point] = []
    idx = min_idx
    max_iterations = n + 1
    iterations = 0
    while True:
        side1.append(pts[idx])
        if idx == max_idx:
            break
        idx = (idx + 1) % n
        iterations += 1
        if iterations > max_iterations:
            return empty

    # 5. Continue from max-angle vertex back to min-angle vertex → side2 (shadow-casting).
    side2: list[Point] = []
    idx = max_idx
    iterations = 0
    while True:
        side2.append(pts[idx])
        if idx == min_idx:
            break
        idx = (idx + 1) % n
        iterations += 1
        if iterations > max_iterations:
            return empty

    # 6. Project the min and max vertices outward along their respective angles.
    min_angle_rad = math.radians(angles[min_idx])
    max_angle_rad = math.radians(angles[max_idx])

    min_projected = Point(
        pts[min_idx].x + canvas_size * math.cos(min_angle_rad),
        pts[min_idx].y - canvas_size * math.sin(min_angle_rad),
    )
    max_projected = Point(
        pts[max_idx].x + canvas_size * math.cos(max_angle_rad),
        pts[max_idx].y - canvas_size * math.sin(max_angle_rad),
    )

    # 7. Assemble: shadow = [max_projected] + side2 + [min_projected]
    shadow = tuple([max_projected, *side2, min_projected])
    sun_facing = tuple(side1)

    return shadow, sun_facing


def clamp_to_circle(polygon: Polygon, center: Point, radius: float) -> Polygon:
    """Clamp polygon points that exceed the circle boundary.

    Performs per-point radial clamping, not true geometric clipping. Points
    outside the circle are moved to the boundary along their radial vector;
    no new intersection vertices are introduced at the crossing edge.
    """
    if not polygon:
        return ()
    result: list[Point] = []
    for p in polygon:
        dx = p.x - center.x
        dy = p.y - center.y
        dist = math.hypot(dx, dy)
        if dist > radius:
            scale = radius / dist
            result.append(Point(center.x + dx * scale, center.y + dy * scale))
        else:
            result.append(p)
    return tuple(result)


def compute_building_shadows(
    geometry: GeometryConfig, sun: SunPosition
) -> list[ShadowResult]:
    """Compute shadow projections for all buildings in the geometry."""
    if sun.elevation <= 0 or sun.elevation >= 90:
        return []

    adjusted_azimuth = apply_north_rotation(sun.azimuth, geometry.canvas.north_rotation)
    center = Point(geometry.canvas.size / 2, geometry.canvas.size / 2)
    radius = geometry.canvas.size / 2

    results: list[ShadowResult] = []
    for building in geometry.buildings:
        if not building.casts_shadow:
            continue
        shadow, sun_facing = compute_shadow_polygon(
            building.vertices, adjusted_azimuth, sun.elevation, geometry.canvas.size
        )
        shadow = clamp_to_circle(shadow, center, radius)
        if shadow:
            results.append(
                ShadowResult(
                    building_name=building.name,
                    shadow_polygon=shadow,
                    sun_facing_edges=sun_facing,
                )
            )
    return results
