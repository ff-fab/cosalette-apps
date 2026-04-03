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

"""Unit tests for app.py — composition root and telemetry handler.

Test Techniques Used:
- Specification-based: factory returns correctly wired App instance
- State Verification: pipeline state built from settings overrides
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cosalette
import pytest

from suncast.app import PipelineState, _build_pipeline, create_app
from suncast.domain.geometry import BuildingConfig, CanvasConfig, GeometryConfig
from suncast.output import OutputManager
from suncast.renderer import RenderSettings, ShadowRenderer
from suncast.settings import SuncastSettings


def _make_settings(**overrides: object) -> SuncastSettings:
    defaults: dict[str, object] = {
        "latitude": 50.0,
        "longitude": 8.0,
        "timezone": "Europe/Berlin",
    }
    defaults.update(overrides)
    return SuncastSettings(**defaults)  # type: ignore[arg-type]


_TEST_GEOMETRY = GeometryConfig(
    canvas=CanvasConfig(size=100),
    buildings=[
        BuildingConfig(
            name="house",
            vertices=[(30, 30), (70, 30), (70, 70), (30, 70)],
        ),
    ],
)


@pytest.mark.unit
class TestCreateApp:
    """create_app() produces a correctly wired cosalette App."""

    def test_returns_app_instance(self) -> None:
        app = create_app()
        assert isinstance(app, cosalette.App)

    def test_app_name(self) -> None:
        app = create_app()
        assert app._name == "suncast"

    def test_settings_class(self) -> None:
        app = create_app()
        assert app._settings_class is SuncastSettings


@pytest.mark.unit
class TestBuildPipeline:
    """The init callback builds pipeline state from settings."""

    def test_returns_pipeline_state(self) -> None:
        settings = _make_settings(geometry_file=Path("unused.yaml"))
        with patch("suncast.app.load_geometry", return_value=_TEST_GEOMETRY):
            state = _build_pipeline(settings)

        assert isinstance(state, PipelineState)
        assert state.geometry is _TEST_GEOMETRY
        assert isinstance(state.renderer, ShadowRenderer)
        assert isinstance(state.render_settings, RenderSettings)
        assert isinstance(state.output_manager, OutputManager)

    def test_render_settings_from_settings(self) -> None:
        settings = _make_settings(
            geometry_file=Path("unused.yaml"),
            primary_color="#aaa",
            stroke_width=3.0,
            sundial_mode="compact",
        )
        with patch("suncast.app.load_geometry", return_value=_TEST_GEOMETRY):
            state = _build_pipeline(settings)

        assert state.render_settings.primary_color == "#aaa"
        assert state.render_settings.stroke_width == 3.0
        assert state.render_settings.sundial_mode == "compact"
