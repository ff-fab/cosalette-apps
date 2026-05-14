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
- Specification-based: module-level App is wired with decorator telemetry
- State Verification: pipeline state built from settings overrides
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import cosalette
import pytest

from suncast.app import PipelineState, _build_pipeline, _poll_interval, app, create_app
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
    """Module-level app exposes a correctly wired cosalette App."""

    def test_returns_app_instance(self) -> None:
        assert isinstance(app, cosalette.App)

    def test_create_app_returns_module_app(self) -> None:
        assert create_app() is app

    def test_app_name(self) -> None:
        assert app._name == "suncast"

    def test_settings_class(self) -> None:
        assert app._settings_class is SuncastSettings

    def test_shadow_telemetry_registered_declaratively(self) -> None:
        registrations = [r for r in app.telemetry_registrations if r.name == "shadow"]
        assert len(registrations) == 1
        assert registrations[0].func is not None
        assert registrations[0].interval is _poll_interval
        assert registrations[0].init is _build_pipeline


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


@pytest.mark.unit
class TestPollInterval:
    """_poll_interval() — deferred interval resolver."""

    def test_returns_poll_interval_from_settings(self) -> None:
        """Happy path: returns poll_interval from SuncastSettings.

        Technique: Specification-based — verifies the deferred resolver contract.
        """
        settings = _make_settings(poll_interval=30.0)
        assert _poll_interval(settings) == 30.0

    def test_raises_type_error_for_wrong_settings_type(self) -> None:
        """Error Guessing: a plain cosalette.Settings raises TypeError.

        _poll_interval is called by the framework with the app's settings object.
        If the framework ever passes the wrong type, the guard must catch it
        before a silent AttributeError or incorrect value is returned downstream.
        """
        wrong = cosalette.Settings()
        with pytest.raises(TypeError, match="Expected SuncastSettings"):
            _poll_interval(wrong)
