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
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator


class CanvasConfig(BaseModel):
    """Canvas dimensions for the shadow visualization grid."""

    model_config = ConfigDict(frozen=True)

    size: int = 100
    """Side length of the square canvas (0..size inclusive)."""


class HighlightedRegion(BaseModel):
    """A named rectangular region to highlight on the canvas."""

    model_config = ConfigDict(frozen=True)

    name: str
    x: int
    y: int
    width: int
    height: int


class BuildingConfig(BaseModel):
    """A named building defined by its polygon vertices and height."""

    model_config = ConfigDict(frozen=True)

    name: str
    height: float
    vertices: list[tuple[int, int]]


class GeometryConfig(BaseModel):
    """Top-level geometry configuration combining canvas, buildings, and highlights."""

    model_config = ConfigDict(frozen=True)

    canvas: CanvasConfig = CanvasConfig()
    buildings: list[BuildingConfig]
    highlighted_regions: list[HighlightedRegion] = []

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
            if region.x < 0 or region.y < 0:
                msg = f"Highlighted region '{region.name}' has negative origin ({region.x}, {region.y})"
                raise ValueError(msg)
            if region.x + region.width > size or region.y + region.height > size:
                msg = f"Highlighted region '{region.name}' extends outside canvas bounds (0..{size})"
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
    text = path.read_text(encoding="utf-8")

    data: Any
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    elif suffix == ".json":
        data = json.loads(text)
    else:
        msg = f"Unsupported file extension '{suffix}'. Use .yaml, .yml, or .json."
        raise ValueError(msg)

    if data is None:
        data = {}

    return GeometryConfig.model_validate(data)
