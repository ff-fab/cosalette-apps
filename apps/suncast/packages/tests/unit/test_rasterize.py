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

"""Unit tests for rasterize.py — PNG rasterization from SVG content.

Test Techniques Used:
- Specification-based: svg_to_png contract and return type
- Error Guessing: Missing cairosvg dependency, conversion failure
- Boundary Value Analysis: Custom width/height dimensions
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from suncast.rasterize import RasterizationError, svg_to_png


# =============================================================================
# Fixtures
# =============================================================================

MINIMAL_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


@pytest.fixture()
def mock_cairosvg() -> MagicMock:
    """A mock cairosvg module returning valid PNG bytes."""
    mock = MagicMock()
    mock.svg2png.return_value = b"\x89PNG\r\n\x1a\nfake"
    return mock


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
class TestSvgToPngWithCairosvg:
    """Tests for svg_to_png when cairosvg is available.

    Technique: Specification-based — verifying the public API contract.
    """

    def test_returns_bytes(self, mock_cairosvg: MagicMock) -> None:
        """svg_to_png returns bytes when cairosvg is available."""
        # Arrange / Act
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock_cairosvg),
        ):
            result = svg_to_png(MINIMAL_SVG)

        # Assert
        assert isinstance(result, bytes)
        assert result == b"\x89PNG\r\n\x1a\nfake"

    def test_passes_dimensions_to_cairosvg(self, mock_cairosvg: MagicMock) -> None:
        """svg_to_png forwards width and height to cairosvg.svg2png.

        Technique: Specification-based — parameter forwarding.
        """
        # Arrange / Act
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock_cairosvg),
        ):
            svg_to_png(MINIMAL_SVG, width=1024, height=768)

        # Assert
        call_kwargs = mock_cairosvg.svg2png.call_args[1]
        assert call_kwargs["output_width"] == 1024
        assert call_kwargs["output_height"] == 768

    def test_uses_default_dimensions(self, mock_cairosvg: MagicMock) -> None:
        """svg_to_png uses 800x800 when no dimensions are specified.

        Technique: Boundary Value Analysis — default dimensions.
        """
        # Arrange / Act
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock_cairosvg),
        ):
            svg_to_png(MINIMAL_SVG)

        # Assert
        call_kwargs = mock_cairosvg.svg2png.call_args[1]
        assert call_kwargs["output_width"] == 800
        assert call_kwargs["output_height"] == 800

    def test_encodes_svg_as_utf8(self, mock_cairosvg: MagicMock) -> None:
        """svg_to_png passes SVG content as UTF-8 encoded bytes.

        Technique: Specification-based — encoding contract.
        """
        # Arrange / Act
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock_cairosvg),
        ):
            svg_to_png(MINIMAL_SVG)

        # Assert
        call_kwargs = mock_cairosvg.svg2png.call_args[1]
        assert call_kwargs["bytestring"] == MINIMAL_SVG.encode("utf-8")


@pytest.mark.unit
class TestSvgToPngWithoutCairosvg:
    """Tests for svg_to_png when cairosvg is not installed.

    Technique: Error Guessing — missing optional dependency.
    """

    def test_raises_rasterization_error(self) -> None:
        """svg_to_png raises RasterizationError with install hint."""
        # Arrange / Act / Assert
        with (
            patch("suncast.rasterize._cairosvg_available", False),
            pytest.raises(RasterizationError, match="'png' extra"),
        ):
            svg_to_png(MINIMAL_SVG)


@pytest.mark.unit
class TestSvgToPngConversionFailure:
    """Tests for svg_to_png when cairosvg raises during conversion.

    Technique: Error Guessing — cairosvg internal failure.
    """

    def test_wraps_cairosvg_exception(self) -> None:
        """Conversion exceptions are wrapped in RasterizationError."""
        # Arrange
        mock = MagicMock()
        mock.svg2png.side_effect = ValueError("bad SVG")

        # Act / Assert
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock),
            pytest.raises(RasterizationError, match="SVG-to-PNG conversion failed"),
        ):
            svg_to_png(MINIMAL_SVG)

    def test_preserves_original_exception(self) -> None:
        """Original exception is chained via __cause__.

        Technique: Error Guessing — exception chain preservation.
        """
        # Arrange
        original = ValueError("bad SVG")
        mock = MagicMock()
        mock.svg2png.side_effect = original

        # Act / Assert
        with (
            patch("suncast.rasterize._cairosvg_available", True),
            patch("suncast.rasterize.cairosvg", mock),
            pytest.raises(RasterizationError) as exc_info,
        ):
            svg_to_png(MINIMAL_SVG)

        assert exc_info.value.__cause__ is original
