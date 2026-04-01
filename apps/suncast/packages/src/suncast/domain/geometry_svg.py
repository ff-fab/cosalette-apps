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

"""SVG geometry importer for building and canvas configuration.

Parses SVG files containing <polygon> and <path> elements (straight-line
segments only) and converts them into a GeometryConfig.  An optional YAML
sidecar maps shape names to building/highlight roles.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from suncast.domain.geometry import (
    BuildingConfig,
    CanvasConfig,
    GeometryConfig,
    HighlightedRegion,
)

logger = logging.getLogger(__name__)

# SVG / Inkscape namespaces
_NS_SVG = "http://www.w3.org/2000/svg"
_NS_INKSCAPE = "http://www.inkscape.org/namespaces/inkscape"

# Path commands that represent curves (unsupported).
_CURVE_COMMANDS = set("CcSsQqTtAa")

# Regex to tokenise an SVG path 'd' attribute.
_PATH_TOKEN_RE = re.compile(
    r"([MmLlHhVvZz])|([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)"
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _shape_name(element: ET.Element, index: int) -> str:
    """Derive a shape name from element attributes or generate one.

    Priority: id > inkscape:label > data-name > auto-generated.
    """
    name = element.get("id")
    if name:
        return name

    name = element.get(f"{{{_NS_INKSCAPE}}}label")
    if name:
        return name

    name = element.get("data-name")
    if name:
        return name

    return f"shape_{index}"


def _parse_polygon_points(points_attr: str) -> list[tuple[float, float]]:
    """Parse the 'points' attribute of a <polygon> into vertex tuples."""
    vertices: list[tuple[float, float]] = []
    for pair in points_attr.strip().split():
        parts = pair.split(",")
        if len(parts) == 2:
            vertices.append((float(parts[0]), float(parts[1])))
    return vertices


def _parse_path_d(d_attr: str) -> list[tuple[float, float]] | None:
    """Parse an SVG path 'd' attribute supporting only straight-line commands.

    Returns vertex list on success, or ``None`` if unsupported commands are
    found (the caller should skip the element).
    """
    # Reject early if any curve command is present.
    for ch in d_attr:
        if ch in _CURVE_COMMANDS:
            return None

    tokens = _PATH_TOKEN_RE.findall(d_attr)

    vertices: list[tuple[float, float]] = []
    cx, cy = 0.0, 0.0  # current point
    cmd = ""

    nums: list[float] = []

    def _flush() -> None:
        """Process accumulated numbers for the current command."""
        nonlocal cx, cy

        if not cmd or cmd in ("Z", "z"):
            return

        i = 0
        while i < len(nums):
            if cmd == "M":
                cx, cy = nums[i], nums[i + 1]
                vertices.append((cx, cy))
                i += 2
            elif cmd == "m":
                cx += nums[i]
                cy += nums[i + 1]
                vertices.append((cx, cy))
                i += 2
            elif cmd == "L":
                cx, cy = nums[i], nums[i + 1]
                vertices.append((cx, cy))
                i += 2
            elif cmd == "l":
                cx += nums[i]
                cy += nums[i + 1]
                vertices.append((cx, cy))
                i += 2
            elif cmd == "H":
                cx = nums[i]
                vertices.append((cx, cy))
                i += 1
            elif cmd == "h":
                cx += nums[i]
                vertices.append((cx, cy))
                i += 1
            elif cmd == "V":
                cy = nums[i]
                vertices.append((cx, cy))
                i += 1
            elif cmd == "v":
                cy += nums[i]
                vertices.append((cx, cy))
                i += 1
            else:
                break  # safety — should not happen

    for cmd_match, num_match in tokens:
        if cmd_match:
            _flush()
            nums = []
            cmd = cmd_match
        elif num_match:
            nums.append(float(num_match))

    _flush()

    return vertices


def _parse_viewbox(svg_root: ET.Element) -> tuple[float, float, float, float] | None:
    """Extract viewBox (min-x, min-y, width, height) or None."""
    vb = svg_root.get("viewBox")
    if not vb:
        return None
    parts = vb.replace(",", " ").split()
    if len(parts) != 4:
        return None
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def _canvas_size_from_svg(svg_root: ET.Element) -> int:
    """Determine canvas size from SVG viewBox, width/height, or default 100."""
    vb = _parse_viewbox(svg_root)
    if vb is not None:
        return int(max(vb[2], vb[3]))

    w = svg_root.get("width")
    h = svg_root.get("height")
    if w is not None and h is not None:
        try:
            return int(max(float(w), float(h)))
        except ValueError:
            pass

    return 100


def _transform_vertices(
    vertices: list[tuple[float, float]],
    viewbox: tuple[float, float, float, float] | None,
    canvas_size: int,
) -> list[tuple[float, float]]:
    """Transform SVG coordinates to canvas coordinates using viewBox."""
    if viewbox is None:
        return vertices

    min_x, min_y, vb_w, vb_h = viewbox
    scale = canvas_size / max(vb_w, vb_h)

    return [((x - min_x) * scale, (y - min_y) * scale) for x, y in vertices]


# ---------------------------------------------------------------------------
# Sidecar loading
# ---------------------------------------------------------------------------


def _load_sidecar(path: Path | None) -> dict[str, Any]:
    """Load and return sidecar YAML, or empty dict if None / missing."""
    if path is None or not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_svg_geometry(
    svg_path: Path,
    sidecar_path: Path | None = None,
) -> GeometryConfig:
    """Load geometry from an SVG file with an optional YAML sidecar.

    Args:
        svg_path: Path to the ``.svg`` file.
        sidecar_path: Optional path to a YAML sidecar that maps shape names
            to building / highlighted-region properties.

    Returns:
        A validated, frozen :class:`GeometryConfig`.

    Raises:
        FileNotFoundError: If *svg_path* does not exist.
        ValueError: If the SVG contains no usable shapes or validation fails.
    """
    if not svg_path.exists():
        msg = f"SVG file not found: {svg_path}"
        raise FileNotFoundError(msg)

    tree = ET.parse(svg_path)  # noqa: S314 — trusted local files only
    root = tree.getroot()

    sidecar = _load_sidecar(sidecar_path)
    shape_roles: dict[str, dict[str, Any]] = sidecar.get("shape_roles", {})

    # Canvas -----------------------------------------------------------
    sidecar_canvas = sidecar.get("canvas", {}) or {}
    svg_canvas_size = _canvas_size_from_svg(root)
    canvas_size = int(sidecar_canvas.get("size", svg_canvas_size))
    north_rotation = float(sidecar_canvas.get("north_rotation", 0.0))
    canvas = CanvasConfig(size=canvas_size, north_rotation=north_rotation)

    viewbox = _parse_viewbox(root)

    # Extract shapes ---------------------------------------------------
    buildings: list[BuildingConfig] = []
    highlights: list[HighlightedRegion] = []
    shape_counter = 1

    elements: list[ET.Element] = []
    elements.extend(root.iter(f"{{{_NS_SVG}}}polygon"))
    elements.extend(root.iter("polygon"))
    elements.extend(root.iter(f"{{{_NS_SVG}}}path"))
    elements.extend(root.iter("path"))

    # Deduplicate (an element may match both namespaced and bare queries).
    seen_ids: set[int] = set()
    unique_elements: list[ET.Element] = []
    for el in elements:
        eid = id(el)
        if eid not in seen_ids:
            seen_ids.add(eid)
            unique_elements.append(el)

    for el in unique_elements:
        tag_local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        name = _shape_name(el, shape_counter)

        # Parse vertices depending on element type.
        verts: list[tuple[float, float]] | None = None
        if tag_local == "polygon":
            points = el.get("points", "")
            verts = _parse_polygon_points(points) if points else None
        elif tag_local == "path":
            d = el.get("d", "")
            if d:
                verts = _parse_path_d(d)
                if verts is None:
                    logger.warning(
                        "Skipping path '%s': contains unsupported curve commands",
                        name,
                    )
                    shape_counter += 1
                    continue

        if not verts or len(verts) < 3:
            shape_counter += 1
            continue

        verts = _transform_vertices(verts, viewbox, canvas_size)

        # Determine role from sidecar.
        role = shape_roles.get(name, {})
        is_highlighted = role.get("highlighted", False)

        if is_highlighted:
            color = str(role.get("color", "#ffff00"))
            highlights.append(
                HighlightedRegion(name=name, vertices=verts, color=color),
            )
        else:
            casts_shadow = bool(role.get("casts_shadow", True))
            style = role.get("style", "default")
            buildings.append(
                BuildingConfig(
                    name=name,
                    vertices=verts,
                    casts_shadow=casts_shadow,
                    style=style,
                ),
            )

        shape_counter += 1

    if not buildings:
        msg = "SVG contains no usable building shapes (need at least one polygon or straight-line path with >= 3 vertices)"
        raise ValueError(msg)

    return GeometryConfig(
        canvas=canvas,
        buildings=buildings,
        highlighted_regions=highlights,
    )
