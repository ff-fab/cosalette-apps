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

"""Integration tests for the suncast full pipeline.

Test Techniques Used:
- Scenario/State: daytime vs. nighttime cycles with fixed datetime
- Specification-based: SVG structure verification (shadow groups, paths)
- Error Guessing: missing geometry file, missing shadows at night
- Integration: real domain objects with mocked time and DeviceContext
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import cosalette
import pytest

from suncast.app import PipelineState, _build_pipeline, _shadow_handler
from suncast.domain.geometry import BuildingConfig, CanvasConfig, GeometryConfig
from suncast.output import OutputManager, OutputSettings
from suncast.renderer import RenderSettings, ShadowRenderer
from suncast.settings import SuncastSettings

# -- Zurich location (randomized European location) -----------------------

_LAT = 47.3769
_LON = 8.5417
_TZ = "Europe/Zurich"

# -- Building geometry adapted to GeometryConfig ---------------------------

TEST_GEOMETRY = GeometryConfig(
    canvas=CanvasConfig(size=100),
    buildings=[
        BuildingConfig(
            name="home",
            vertices=[
                (50.75, 33.75),
                (80.00, 52.25),
                (67.25, 72.50),
                (70.75, 75.00),
                (62.00, 89.00),
                (54.75, 90.50),
                (26.50, 72.75),
            ],
            casts_shadow=True,
            style="home",
        ),
        BuildingConfig(
            name="neighbor",
            vertices=[
                (4.75, 59.00),
                (10.50, 49.75),
                (6.75, 47.50),
                (18.25, 29.25),
                (22.00, 31.50),
                (32.00, 15.25),
                (54.00, 28.75),
                (26.75, 72.75),
            ],
            casts_shadow=True,
            style="default",
        ),
        BuildingConfig(
            name="northeast",
            vertices=[
                (56.50, 37.40),
                (70.00, 16.00),
                (99.25, 34.25),
                (93.00, 55.75),
                (90.75, 59.00),
            ],
            casts_shadow=True,
            style="neighbor",
        ),
    ],
    highlighted_regions=[],
)


def _make_settings(**overrides: object) -> SuncastSettings:
    """Create SuncastSettings with sensible defaults for integration tests."""
    defaults: dict[str, object] = {
        "latitude": _LAT,
        "longitude": _LON,
        "timezone": _TZ,
    }
    defaults.update(overrides)
    return SuncastSettings(**defaults)  # type: ignore[arg-type]


def _make_pipeline(
    tmp_path: Path,
    *,
    geometry: GeometryConfig = TEST_GEOMETRY,
    png_enabled: bool = False,
) -> PipelineState:
    """Build a PipelineState with filesystem output routed to *tmp_path*."""
    output_settings = OutputSettings(
        output_path=tmp_path,
        png_enabled=png_enabled,
    )
    return PipelineState(
        geometry=geometry,
        renderer=ShadowRenderer(),
        render_settings=RenderSettings(),
        output_manager=OutputManager(output_settings),
    )


def _make_ctx() -> MagicMock:
    """Create a mock DeviceContext with an async publish method."""
    ctx = MagicMock(spec=cosalette.DeviceContext)
    ctx.publish = AsyncMock()
    return ctx


# -- Daytime: June 21 at noon (summer solstice, guaranteed daylight) -------
_DAYTIME = datetime(2026, 6, 21, 12, 0, 0, tzinfo=ZoneInfo(_TZ))
# -- Nighttime: June 21 at midnight ----------------------------------------
_NIGHTTIME = datetime(2026, 6, 21, 0, 0, 0, tzinfo=ZoneInfo(_TZ))


@pytest.mark.integration
class TestFullCycle:
    """Full daytime cycle — SVG with shadows, filesystem output, MQTT."""

    async def test_svg_published_to_mqtt(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _DAYTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — MQTT SVG channel received valid SVG
        svg_calls = [c for c in ctx.publish.call_args_list if c.args[0] == "svg"]
        assert len(svg_calls) == 1
        svg_content = svg_calls[0].args[1]
        assert isinstance(svg_content, str)
        assert "<svg" in svg_content
        assert "</svg>" in svg_content

    async def test_svg_file_written(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _DAYTIME
            await _shadow_handler(ctx, state, settings)

        # Assert
        svg_file = tmp_path / "shadow.svg"
        assert svg_file.exists()
        content = svg_file.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "</svg>" in content

    async def test_daytime_svg_contains_shadows(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _DAYTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — SVG contains shadow polygons
        svg_content = (tmp_path / "shadow.svg").read_text(encoding="utf-8")
        assert 'class="shadows"' in svg_content


@pytest.mark.integration
class TestNightCycle:
    """Nighttime cycle — SVG produced but no shadow polygons."""

    async def test_svg_produced_at_night(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _NIGHTTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — SVG is still produced with buildings and sundial
        svg_content = (tmp_path / "shadow.svg").read_text(encoding="utf-8")
        assert "<svg" in svg_content
        assert "</svg>" in svg_content
        assert 'class="buildings"' in svg_content

    async def test_no_shadows_at_night(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _NIGHTTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — no shadow group in the SVG
        svg_content = (tmp_path / "shadow.svg").read_text(encoding="utf-8")
        assert 'class="shadows"' not in svg_content


@pytest.mark.integration
class TestMultipleBuildings:
    """Multiple buildings each cast a shadow path during daytime."""

    async def test_each_building_casts_shadow(self, tmp_path: Path) -> None:
        # Arrange — TEST_GEOMETRY has 3 shadow-casting buildings
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path)
        settings = _make_settings()

        # Act
        with patch("suncast.app.datetime") as mock_dt:
            mock_dt.now.return_value = _DAYTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — shadow group has at least 3 path elements
        svg_content = (tmp_path / "shadow.svg").read_text(encoding="utf-8")
        assert 'class="shadows"' in svg_content
        # Each shadow-casting building produces a <path> inside the shadows group
        shadow_start = svg_content.index('class="shadows"')
        shadow_section = svg_content[
            shadow_start : svg_content.index("</g>", shadow_start)
        ]
        path_count = shadow_section.count("<path")
        assert path_count >= 3, f"Expected ≥3 shadow paths, got {path_count}"


@pytest.mark.integration
class TestPngOutput:
    """PNG output — filesystem and MQTT when enabled."""

    async def test_png_file_and_mqtt(self, tmp_path: Path) -> None:
        # Arrange
        ctx = _make_ctx()
        state = _make_pipeline(tmp_path, png_enabled=True)
        settings = _make_settings()
        fake_png = b"\x89PNG\r\n\x1a\nfake"

        # Act — mock svg_to_png since cairosvg may not be available
        with (
            patch("suncast.app.datetime") as mock_dt,
            patch("suncast.output.svg_to_png", return_value=fake_png),
        ):
            mock_dt.now.return_value = _DAYTIME
            await _shadow_handler(ctx, state, settings)

        # Assert — PNG file written
        png_file = tmp_path / "shadow.png"
        assert png_file.exists()
        assert png_file.read_bytes() == fake_png

        # Assert — PNG published to MQTT (base64-encoded)
        png_calls = [c for c in ctx.publish.call_args_list if c.args[0] == "png"]
        assert len(png_calls) == 1


@pytest.mark.integration
class TestGeometryFileNotFound:
    """Non-existent geometry file raises a clear error."""

    def test_build_pipeline_raises_on_missing_file(self) -> None:
        settings = _make_settings(
            geometry_file=Path("/nonexistent/path/geometry.yaml"),
        )
        with pytest.raises(FileNotFoundError):
            _build_pipeline(settings)
