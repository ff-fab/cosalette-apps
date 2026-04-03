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

"""YAML/JSON geometry loader for building and canvas configuration."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class CanvasConfig(BaseModel):
    """Canvas dimensions for the shadow visualization grid."""

    model_config = ConfigDict(frozen=True)

    size: int = Field(default=100, ge=1)
    """Side length of the square canvas (0..size inclusive)."""

    north_rotation: float = 0.0
    """Compass rotation offset in degrees."""


class BuildingConfig(BaseModel):
    """A named building defined by its polygon vertices."""

    model_config = ConfigDict(frozen=True)

    name: str
    vertices: list[tuple[float, float]]
    casts_shadow: bool = True
    style: Literal["home", "neighbor", "default"] = "default"


class HighlightedRegion(BaseModel):
    """A named polygon region to highlight on the canvas."""

    model_config = ConfigDict(frozen=True)

    name: str
    vertices: list[tuple[float, float]]
    color: str


class GeometryConfig(BaseModel):
    """Top-level geometry configuration combining canvas, buildings, and highlights."""

    model_config = ConfigDict(frozen=True)

    canvas: CanvasConfig = Field(default_factory=CanvasConfig)
    buildings: list[BuildingConfig]
    highlighted_regions: list[HighlightedRegion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_geometry(self) -> GeometryConfig:
        """Cross-field validation: vertex bounds and shape constraints."""
        if len(self.buildings) < 1:
            msg = "At least one building is required"
            raise ValueError(msg)

        size = self.canvas.size
        for building in self.buildings:
            if len(building.vertices) < 3:
                msg = f"Building '{building.name}' must have at least 3 vertices, got {len(building.vertices)}"
                raise ValueError(msg)
            for x, y in building.vertices:
                if not (0 <= x <= size and 0 <= y <= size):
                    msg = f"Building '{building.name}' vertex ({x}, {y}) is outside canvas bounds (0..{size})"
                    raise ValueError(msg)

        for region in self.highlighted_regions:
            if len(region.vertices) < 3:
                msg = f"Highlighted region '{region.name}' must have at least 3 vertices, got {len(region.vertices)}"
                raise ValueError(msg)
            for x, y in region.vertices:
                if not (0 <= x <= size and 0 <= y <= size):
                    msg = f"Highlighted region '{region.name}' vertex ({x}, {y}) is outside canvas bounds (0..{size})"
                    raise ValueError(msg)

        return self


def load_geometry(path: Path) -> GeometryConfig:
    """Load and validate geometry from a YAML or JSON file.

    Args:
        path: Path to a .yaml, .yml, or .json geometry file.

    Returns:
        A validated, frozen GeometryConfig.

    Raises:
        ValueError: If the file extension is unsupported or validation fails.
        FileNotFoundError: If the file does not exist.
    """
    suffix = path.suffix.lower()
    if suffix not in (".yaml", ".yml", ".json"):
        msg = f"Unsupported file extension '{suffix}'. Use .yaml, .yml, or .json."
        raise ValueError(msg)

    text = path.read_text(encoding="utf-8")

    data: Any
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    if data is None:
        data = {}

    try:
        return GeometryConfig.model_validate(data)
    except ValidationError as exc:
        msg = str(exc)
        raise ValueError(msg) from exc


def fit_to_circle(
    geometry: GeometryConfig,
    *,
    padding_fraction: float = 0.18,
) -> GeometryConfig:
    """Scale all vertices so every point fits within the canvas circle.

    Computes the maximum distance of any vertex from the canvas center.
    If that distance exceeds ``radius - padding``, all vertex coordinates
    are uniformly scaled (relative to the center) to fit.

    Args:
        geometry: The original geometry configuration.
        padding_fraction: Padding as a fraction of the radius (default 18%).

    Returns:
        A new GeometryConfig with scaled coordinates, or the original
        if all vertices already fit.
    """
    canvas = geometry.canvas.size
    cx, cy = canvas / 2, canvas / 2
    radius = canvas / 2
    fit_radius = radius * (1 - padding_fraction)

    # Collect all vertices from buildings and highlighted regions.
    all_vertices: list[tuple[float, float]] = []
    for b in geometry.buildings:
        all_vertices.extend(b.vertices)
    for hr in geometry.highlighted_regions:
        all_vertices.extend(hr.vertices)

    if not all_vertices:
        return geometry

    # Find the maximum distance from center.
    max_dist = max(math.hypot(x - cx, y - cy) for x, y in all_vertices)

    if max_dist <= fit_radius:
        return geometry  # Already fits, no scaling needed.

    scale = fit_radius / max_dist

    def _scale_vertices(
        vertices: list[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        return [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in vertices]

    scaled_buildings = [
        BuildingConfig(
            name=b.name,
            vertices=_scale_vertices(b.vertices),
            casts_shadow=b.casts_shadow,
            style=b.style,
        )
        for b in geometry.buildings
    ]

    scaled_regions = [
        HighlightedRegion(
            name=hr.name,
            vertices=_scale_vertices(hr.vertices),
            color=hr.color,
        )
        for hr in geometry.highlighted_regions
    ]

    return GeometryConfig(
        canvas=geometry.canvas,
        buildings=scaled_buildings,
        highlighted_regions=scaled_regions,
    )
