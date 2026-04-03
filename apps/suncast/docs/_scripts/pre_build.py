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

"""Generate documentation images from suncast business logic.

Produces SVG shadow visualizations for the documentation site so that
images stay in sync with the actual rendering code.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from suncast.domain.geometry import (
    BuildingConfig,
    CanvasConfig,
    GeometryConfig,
    fit_to_circle,
    load_geometry,
)
from suncast.domain.shadow import compute_building_shadows
from suncast.domain.solar import compute_solar_position
from suncast.renderer import RenderSettings, ShadowRenderer

SCRIPT_DIR = Path(__file__).resolve().parent
GEOMETRY_PATH = SCRIPT_DIR / "../../geometry.example.yaml"
OUTPUT_DIR = SCRIPT_DIR / "../images/generated"

LAT = 50.1
LON = 8.68
TZ = "Europe/Berlin"
DATE = datetime(2026, 6, 21, tzinfo=ZoneInfo(TZ))

renderer = ShadowRenderer()


def _make_dt(hour: int, minute: int = 0) -> datetime:
    return DATE.replace(hour=hour, minute=minute)


def _render(
    geometry: GeometryConfig,
    dt_obj: datetime,
    settings: RenderSettings | None = None,
) -> str:
    sun = compute_solar_position(LAT, LON, TZ, dt_obj)
    shadows = compute_building_shadows(geometry, sun)
    return renderer.render(sun, shadows, geometry, settings)


def _write(name: str, svg: str) -> Path:
    path = OUTPUT_DIR / name
    path.write_text(svg, encoding="utf-8")
    return path


def generate_showcase(geometry: GeometryConfig) -> list[Path]:
    """Four times-of-day with default settings."""
    times = [
        ("showcase-morning.svg", 8, 0),
        ("showcase-noon.svg", 12, 0),
        ("showcase-afternoon.svg", 16, 30),
        ("showcase-night.svg", 22, 0),
    ]
    return [_write(name, _render(geometry, _make_dt(h, m))) for name, h, m in times]


def generate_config_comparison(geometry: GeometryConfig) -> list[Path]:
    """Marker style and sundial mode comparison images."""
    noon = _make_dt(12)
    return [
        _write(
            "marker-circle.svg",
            _render(geometry, noon, RenderSettings(marker_style="circle")),
        ),
        _write(
            "marker-bar.svg",
            _render(geometry, noon, RenderSettings(marker_style="bar")),
        ),
        _write(
            "sundial-ring.svg",
            _render(geometry, noon, RenderSettings(sundial_mode="ring")),
        ),
        _write(
            "sundial-compact.svg",
            _render(geometry, noon, RenderSettings(sundial_mode="compact")),
        ),
        _write(
            "sundial-off.svg",
            _render(geometry, noon, RenderSettings(sundial_mode="off")),
        ),
    ]


def generate_geometry_guide() -> list[Path]:
    """Convex vs concave building comparison."""
    afternoon = _make_dt(15)
    canvas = CanvasConfig(size=100)

    convex = GeometryConfig(
        canvas=canvas,
        buildings=[
            BuildingConfig(
                name="house",
                vertices=[(35, 30), (65, 30), (65, 70), (35, 70)],
                casts_shadow=True,
                style="home",
            ),
        ],
    )
    convex = fit_to_circle(convex)

    concave = GeometryConfig(
        canvas=canvas,
        buildings=[
            BuildingConfig(
                name="l_shaped",
                vertices=[
                    (30, 25),
                    (60, 25),
                    (60, 50),
                    (45, 50),
                    (45, 75),
                    (30, 75),
                ],
                casts_shadow=True,
                style="home",
            ),
        ],
    )
    concave = fit_to_circle(concave)

    return [
        _write("convex-ok.svg", _render(convex, afternoon)),
        _write("concave-distorted.svg", _render(concave, afternoon)),
    ]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geometry = load_geometry(GEOMETRY_PATH)
    geometry = fit_to_circle(geometry)

    files: list[Path] = []
    files.extend(generate_showcase(geometry))
    files.extend(generate_config_comparison(geometry))
    files.extend(generate_geometry_guide())

    print(f"Generated {len(files)} SVGs in {OUTPUT_DIR}:")
    for f in files:
        print(f"  {f.name}  ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
