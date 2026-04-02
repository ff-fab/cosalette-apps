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

"""PNG rasterization from SVG content.

Uses cairosvg as an optional dependency.  When cairosvg is not installed,
:func:`svg_to_png` raises :class:`RasterizationError` with a clear message
instead of crashing with an opaque ``ImportError``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_cairosvg_available = False
try:
    import cairosvg  # type: ignore[import-not-found]

    _cairosvg_available = True
except ImportError:
    cairosvg = None


class RasterizationError(Exception):
    """Raised when SVG-to-PNG conversion fails."""


def svg_to_png(svg_content: str, *, width: int = 800, height: int = 800) -> bytes:
    """Convert an SVG string to PNG bytes.

    Args:
        svg_content: Raw SVG markup.
        width: Target image width in pixels.
        height: Target image height in pixels.

    Returns:
        PNG image data as bytes.

    Raises:
        RasterizationError: If cairosvg is not installed or conversion fails.
    """
    if not _cairosvg_available:
        msg = (
            "PNG rasterization requires the 'png' extra: "
            "install with `uv pip install suncast[png]`"
        )
        logger.error(msg)
        raise RasterizationError(msg)

    try:
        png_bytes: bytes = cairosvg.svg2png(
            bytestring=svg_content.encode("utf-8"),
            output_width=width,
            output_height=height,
        )
    except Exception as exc:
        msg = f"SVG-to-PNG conversion failed: {exc}"
        raise RasterizationError(msg) from exc

    return png_bytes
