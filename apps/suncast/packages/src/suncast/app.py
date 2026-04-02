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

"""Cosalette application factory for suncast."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import cosalette

from suncast import __version__
from suncast.domain.geometry import GeometryConfig, load_geometry
from suncast.domain.shadow import compute_building_shadows
from suncast.domain.solar import compute_solar_position
from suncast.http_server import HttpSettings, create_http_lifespan
from suncast.output import OutputManager, OutputSettings
from suncast.renderer import RenderSettings, ShadowRenderer
from suncast.settings import SuncastSettings

logger = logging.getLogger(__name__)

_latest_svg: list[str | None] = [None]


@dataclass(frozen=True, slots=True)
class PipelineState:
    """Immutable pipeline state built once per device via ``init=``."""

    geometry: GeometryConfig
    renderer: ShadowRenderer
    render_settings: RenderSettings
    output_manager: OutputManager


def _build_pipeline(settings: SuncastSettings) -> PipelineState:
    """Build pipeline state from settings (invoked as ``init=`` callback)."""
    geometry = load_geometry(settings.geometry_file)
    render_settings = RenderSettings(
        primary_color=settings.primary_color,
        secondary_color=settings.secondary_color,
        light_color=settings.light_color,
        shadow_color=settings.shadow_color,
        stroke_width=settings.stroke_width,
        show_sundial_ring=settings.sundial_ring,
    )
    output_settings = OutputSettings(
        output_path=settings.output_path,
        png_enabled=settings.png_enabled,
        png_width=settings.png_width,
        png_height=settings.png_height,
    )
    return PipelineState(
        geometry=geometry,
        renderer=ShadowRenderer(),
        render_settings=render_settings,
        output_manager=OutputManager(output_settings),
    )


@asynccontextmanager
async def _lifespan(ctx: cosalette.AppContext) -> AsyncIterator[None]:
    """Application lifespan — starts HTTP server if enabled."""
    settings: SuncastSettings = ctx.settings  # type: ignore[assignment]
    http_settings = HttpSettings(
        http_enabled=settings.http_enabled,
        http_host=settings.http_host,
        http_port=settings.http_port,
        png_width=settings.png_width,
        png_height=settings.png_height,
    )
    async with create_http_lifespan(lambda: _latest_svg[0], http_settings):
        yield


async def _shadow_handler(
    ctx: cosalette.DeviceContext,
    state: PipelineState,
    settings: SuncastSettings,
) -> dict[str, object] | None:
    """Telemetry handler — compute shadows and deliver output."""
    now = datetime.now(tz=ZoneInfo(settings.timezone))
    sun = compute_solar_position(
        settings.latitude, settings.longitude, settings.timezone, now
    )
    shadows = compute_building_shadows(state.geometry, sun)
    svg = state.renderer.render(sun, shadows, state.geometry, state.render_settings)

    _latest_svg[0] = svg

    await state.output_manager.deliver(svg, {}, ctx)
    return None


def _poll_interval(s: cosalette.Settings) -> float:
    """Deferred interval — resolved after settings are parsed."""
    assert isinstance(s, SuncastSettings)
    return s.poll_interval


def create_app() -> cosalette.App:
    """Create and wire the suncast cosalette application."""
    app = cosalette.App(
        name="suncast",
        version=__version__,
        description="Sun position and shadow visualization service",
        settings_class=SuncastSettings,
        lifespan=_lifespan,
    )

    app.add_telemetry(
        name="shadow",
        func=_shadow_handler,
        interval=_poll_interval,
        init=_build_pipeline,
    )

    return app
