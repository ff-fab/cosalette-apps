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
    # The ±180° atan2 discontinuity cannot cause wrap-around issues here:
    # the sun reference is ~10 000 units away while buildings span ~20–40 units,
    # giving an angular spread of ~0.2° — far too narrow to straddle the boundary.
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

    # 6. Project silhouette vertices using parallel projection.
    # All shadow edges share the same direction vector (opposite sun azimuth),
    # producing physically accurate parallel shadows.  The renderer's
    # circular mask clips the result visually.
    dir_x = -math.sin(math.radians(sun_azimuth))
    dir_y = math.cos(math.radians(sun_azimuth))

    min_projected = Point(
        pts[min_idx].x + canvas_size * dir_x,
        pts[min_idx].y + canvas_size * dir_y,
    )
    max_projected = Point(
        pts[max_idx].x + canvas_size * dir_x,
        pts[max_idx].y + canvas_size * dir_y,
    )

    # 7. Assemble: shadow = [max_projected] + side2 + [min_projected]
    shadow = tuple([max_projected, *side2, min_projected])
    sun_facing = tuple(side1)

    return shadow, sun_facing


def compute_building_shadows(
    geometry: GeometryConfig, sun: SunPosition
) -> list[ShadowResult]:
    """Compute shadow projections for all buildings in the geometry."""
    if sun.elevation <= 0 or sun.elevation >= 90:
        return []

    adjusted_azimuth = apply_north_rotation(sun.azimuth, geometry.canvas.north_rotation)

    results: list[ShadowResult] = []
    for building in geometry.buildings:
        if not building.casts_shadow:
            continue
        shadow, sun_facing = compute_shadow_polygon(
            building.vertices, adjusted_azimuth, sun.elevation, geometry.canvas.size
        )
        if shadow:
            results.append(
                ShadowResult(
                    building_name=building.name,
                    shadow_polygon=shadow,
                    sun_facing_edges=sun_facing,
                )
            )
    return results
