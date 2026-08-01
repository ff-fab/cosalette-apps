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

"""Application configuration for suncast."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import cosalette
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import SettingsConfigDict

type SundialMode = Literal["ring", "compact", "off"]

# Colors are interpolated directly into SVG output (see renderer.py) without
# escaping, so they're restricted to hex-color syntax to close off SVG/
# attribute injection via a malicious SUNCAST_*_COLOR value.
_HEX_COLOR_PATTERN = r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$"


class RenderStyle(BaseModel):
    """Visual style for the SVG renderer.

    Single source of truth for the render defaults: mixed into
    :class:`SuncastSettings` (so ``SUNCAST_*`` env vars stay flat) and used
    directly by the renderer as its frozen value object, so the palette can't
    drift between the config layer and the renderer.
    """

    # Frozen here; SuncastSettings below explicitly re-sets frozen=False to
    # keep the settings object mutable despite this mixin.
    model_config = ConfigDict(frozen=True)

    primary_color: str = Field(default="#614c1f", pattern=_HEX_COLOR_PATTERN)
    secondary_color: str = Field(default="#b38c3a", pattern=_HEX_COLOR_PATTERN)
    light_color: str = Field(default="#f1b023", pattern=_HEX_COLOR_PATTERN)
    shadow_color: str = Field(default="#2F3338", pattern=_HEX_COLOR_PATTERN)
    stroke_width: float = 1.0
    sundial_mode: SundialMode = "ring"
    marker_style: Literal["circle", "bar"] = "circle"


class SuncastSettings(RenderStyle, cosalette.Settings):
    """Root settings for the suncast application.

    Inherits the render-style fields from :class:`RenderStyle`; ``frozen`` is
    overridden back to ``False`` so settings stay mutable while the standalone
    ``RenderStyle`` value object remains frozen.
    """

    model_config = SettingsConfigDict(
        env_prefix="SUNCAST_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=False,  # counteracts RenderStyle's frozen=True (see class docstring)
    )

    # -- Location (required) ------------------------------------------------

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str

    # -- Geometry -----------------------------------------------------------

    geometry_file: Path = Field(default=Path("geometry.yaml"))

    # -- Timing -------------------------------------------------------------

    poll_interval: float = Field(default=360.0, gt=0)

    # -- Rendering ----------------------------------------------------------
    # Render-style fields (primary_color, …, marker_style) are inherited from
    # RenderStyle above.

    # -- Output -------------------------------------------------------------

    output_path: Path | None = Field(default=Path("/output"))
    png_enabled: bool = False
    png_width: int = Field(default=800, ge=1)
    png_height: int = Field(default=800, ge=1)

    # -- HTTP ---------------------------------------------------------------

    http_enabled: bool = False
    http_host: str = "0.0.0.0"
    http_port: int = Field(default=8080, ge=1, le=65535)
