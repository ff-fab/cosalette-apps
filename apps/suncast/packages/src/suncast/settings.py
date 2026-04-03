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
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class SuncastSettings(cosalette.Settings):
    """Root settings for the suncast application."""

    model_config = SettingsConfigDict(
        env_prefix="SUNCAST_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
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

    primary_color: str = "#614c1f"
    secondary_color: str = "#b38c3a"
    light_color: str = "#f1b023"
    shadow_color: str = "#2F3338"
    stroke_width: float = 1.0
    sundial_ring: bool = True
    marker_style: Literal["circle", "bar"] = "circle"

    # -- Output -------------------------------------------------------------

    output_path: Path | None = Field(default=Path("/output"))
    png_enabled: bool = False
    png_width: int = Field(default=800, ge=1)
    png_height: int = Field(default=800, ge=1)

    # -- HTTP ---------------------------------------------------------------

    http_enabled: bool = False
    http_host: str = "0.0.0.0"  # noqa: S104
    http_port: int = Field(default=8080, ge=1, le=65535)
