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

"""Unit tests for output.py — Output delivery for shadow visualizations.

Test Techniques Used:
- Specification-based: OutputManager.deliver() contract and return value
- Equivalence Partitioning: PNG enabled/disabled, filesystem/MQTT paths
- Error Guessing: Filesystem write failure, MQTT publish failure
- Condition Coverage: All delivery channel combinations
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suncast.output import DeliveryResult, OutputManager, OutputSettings


# =============================================================================
# Fixtures
# =============================================================================

SAMPLE_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
SAMPLE_SUN_STATE: dict[str, object] = {"azimuth": 180.0, "elevation": 45.0}
FAKE_PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture()
def mock_ctx() -> AsyncMock:
    """A mock DeviceContext with async publish."""
    ctx = AsyncMock()
    ctx.publish = AsyncMock()
    return ctx


# =============================================================================
# Tests
# =============================================================================


@pytest.mark.unit
class TestOutputManagerDeliver:
    """Specification-based: deliver() returns sun_state and performs delivery."""

    async def test_returns_sun_state(self) -> None:
        """deliver() returns the sun_state dict unmodified."""
        # Arrange
        manager = OutputManager(OutputSettings())

        # Act
        result = await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        assert result is SAMPLE_SUN_STATE

    async def test_writes_svg_to_filesystem(self, tmp_path: Path) -> None:
        """deliver() writes shadow.svg when output_path is configured."""
        # Arrange
        settings = OutputSettings(output_path=tmp_path)
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        svg_file = tmp_path / "shadow.svg"
        assert svg_file.exists()
        assert svg_file.read_text(encoding="utf-8") == SAMPLE_SVG

    async def test_writes_png_to_filesystem(self, tmp_path: Path) -> None:
        """deliver() writes shadow.png when png_enabled is True.

        Technique: Condition Coverage — PNG filesystem path.
        """
        # Arrange
        settings = OutputSettings(output_path=tmp_path, png_enabled=True)
        manager = OutputManager(settings)

        # Act
        with patch("suncast.output.svg_to_png", return_value=FAKE_PNG):
            await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        png_file = tmp_path / "shadow.png"
        assert png_file.exists()
        assert png_file.read_bytes() == FAKE_PNG

    async def test_no_files_when_output_path_none(self, tmp_path: Path) -> None:
        """deliver() writes no files when output_path is None.

        Technique: Equivalence Partitioning — disabled filesystem output.
        """
        # Arrange
        settings = OutputSettings(output_path=None)
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert — tmp_path should be empty
        assert list(tmp_path.iterdir()) == []

    async def test_no_png_when_disabled(self, tmp_path: Path) -> None:
        """deliver() does not write PNG when png_enabled is False.

        Technique: Condition Coverage — PNG disabled branch.
        """
        # Arrange
        settings = OutputSettings(output_path=tmp_path, png_enabled=False)
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        assert (tmp_path / "shadow.svg").exists()
        assert not (tmp_path / "shadow.png").exists()

    async def test_creates_output_directory(self, tmp_path: Path) -> None:
        """deliver() creates the output directory if it does not exist.

        Technique: Error Guessing — directory does not exist yet.
        """
        # Arrange
        nested = tmp_path / "deeply" / "nested" / "dir"
        settings = OutputSettings(output_path=nested)
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        assert (nested / "shadow.svg").exists()


@pytest.mark.unit
class TestOutputManagerMqtt:
    """Tests for MQTT delivery via DeviceContext.

    Technique: Specification-based — MQTT publish contract.
    """

    async def test_publishes_svg_to_mqtt(self, mock_ctx: AsyncMock) -> None:
        """deliver() publishes SVG to the svg channel."""
        # Arrange
        settings = OutputSettings()
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE, ctx=mock_ctx)

        # Assert
        mock_ctx.publish.assert_any_call("svg", SAMPLE_SVG, retain=True)

    async def test_publishes_png_to_mqtt(self, mock_ctx: AsyncMock) -> None:
        """deliver() publishes PNG bytes to the png channel.

        Technique: Condition Coverage — MQTT PNG path.
        """
        # Arrange
        settings = OutputSettings(png_enabled=True)
        manager = OutputManager(settings)

        # Act
        with patch("suncast.output.svg_to_png", return_value=FAKE_PNG):
            await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE, ctx=mock_ctx)

        # Assert — PNG published as latin-1 decoded string
        mock_ctx.publish.assert_any_call("png", FAKE_PNG.decode("latin-1"), retain=True)

    async def test_no_mqtt_when_ctx_none(self) -> None:
        """deliver() skips MQTT when ctx is None.

        Technique: Equivalence Partitioning — no DeviceContext provided.
        """
        # Arrange
        settings = OutputSettings()
        manager = OutputManager(settings)

        # Act — should not raise
        result = await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE, ctx=None)

        # Assert
        assert result is SAMPLE_SUN_STATE

    async def test_custom_channel_names(self, mock_ctx: AsyncMock) -> None:
        """deliver() uses configured channel names.

        Technique: Specification-based — custom channel name propagation.
        """
        # Arrange
        settings = OutputSettings(
            mqtt_svg_channel="shadow_svg", mqtt_png_channel="shadow_png"
        )
        manager = OutputManager(settings)

        # Act
        await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE, ctx=mock_ctx)

        # Assert
        mock_ctx.publish.assert_any_call("shadow_svg", SAMPLE_SVG, retain=True)


@pytest.mark.unit
class TestOutputManagerErrorHandling:
    """Tests for graceful error handling during delivery.

    Technique: Error Guessing — filesystem and MQTT failures.
    """

    async def test_filesystem_error_does_not_raise(self) -> None:
        """deliver() handles filesystem write failures gracefully."""
        # Arrange — use a path that can't be written to
        settings = OutputSettings(output_path=Path("/nonexistent/readonly/path"))
        manager = OutputManager(settings)

        # Act — should not raise
        result = await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert
        assert result is SAMPLE_SUN_STATE

    async def test_mqtt_error_does_not_raise(self) -> None:
        """deliver() handles MQTT publish failures gracefully."""
        # Arrange
        ctx = AsyncMock()
        ctx.publish = AsyncMock(side_effect=OSError("connection lost"))
        settings = OutputSettings()
        manager = OutputManager(settings)

        # Act — should not raise
        result = await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE, ctx=ctx)

        # Assert
        assert result is SAMPLE_SUN_STATE

    async def test_png_rasterization_error_does_not_raise(self, tmp_path: Path) -> None:
        """deliver() handles PNG rasterization failure gracefully.

        Technique: Error Guessing — cairosvg failure mid-delivery.
        """
        # Arrange
        settings = OutputSettings(output_path=tmp_path, png_enabled=True)
        manager = OutputManager(settings)

        # Act — rasterization will fail because cairosvg is not installed
        with patch(
            "suncast.output.svg_to_png",
            side_effect=MagicMock(
                side_effect=__import__(
                    "suncast.rasterize", fromlist=["RasterizationError"]
                ).RasterizationError("no cairosvg")
            ),
        ):
            result = await manager.deliver(SAMPLE_SVG, SAMPLE_SUN_STATE)

        # Assert — SVG still written, PNG skipped
        assert result is SAMPLE_SUN_STATE
        assert (tmp_path / "shadow.svg").exists()
        assert not (tmp_path / "shadow.png").exists()


@pytest.mark.unit
class TestDeliveryResult:
    """Specification-based: DeliveryResult dataclass defaults.

    Technique: Specification-based — default values.
    """

    def test_defaults(self) -> None:
        """All flags default to False and errors list is empty."""
        # Arrange / Act
        result = DeliveryResult()

        # Assert
        assert result.svg_file_written is False
        assert result.png_file_written is False
        assert result.mqtt_svg_published is False
        assert result.mqtt_png_published is False
        assert result.errors == []


@pytest.mark.unit
class TestOutputSettings:
    """Specification-based: OutputSettings dataclass defaults.

    Technique: Specification-based — default configuration values.
    """

    def test_defaults(self) -> None:
        """OutputSettings has sensible defaults."""
        # Arrange / Act
        settings = OutputSettings()

        # Assert
        assert settings.output_path is None
        assert settings.png_enabled is False
        assert settings.png_width == 800
        assert settings.png_height == 800
        assert settings.mqtt_svg_channel == "svg"
        assert settings.mqtt_png_channel == "png"
