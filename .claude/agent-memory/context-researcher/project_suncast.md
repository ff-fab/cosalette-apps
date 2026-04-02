---
name: suncast project architecture
description:
  Suncast app structure, ADR decisions, module responsibilities, and clean-room
  constraint for shadow geometry
type: project
---

Suncast is a cosalette telemetry app that computes solar positions and generates shadow
SVGs for MQTT delivery.

**Why:** GPL-3.0-or-later clean-room reimplementation. Original forum code
(pmpkk/Patrick, OpenHAB community 2017) has no explicit license — all rights reserved by
default. Legacy code in `jl4services/shadow/image.py` must NOT be referenced.

**How to apply:** Every shadow geometry implementation must derive from first principles
only. Attribution credit must appear in file headers (see ADR-000 wording).

## Module structure

- `apps/suncast/packages/src/suncast/domain/geometry.py` — Pydantic models:
  `CanvasConfig`, `BuildingConfig`, `HighlightedRegion`, `GeometryConfig`; also
  `load_geometry()` loader
- `apps/suncast/packages/src/suncast/domain/solar.py` — `SunPosition` frozen dataclass,
  `compute_solar_position()` using `astral` library
- `apps/suncast/packages/src/suncast/domain/__init__.py` — currently only GPL header
  (nothing exported yet)
- Shadow module to be created at: `apps/suncast/packages/src/suncast/domain/shadow.py`
  (or `shadow.py` under `suncast/`)

## Key data model facts

- Canvas: square 0..size (default 100), north_rotation in degrees clockwise
- Buildings: polygon vertices as `list[tuple[float, float]]`
- Origin (0,0) is top-left corner
- SunPosition: `azimuth` (0-360 clockwise from north), `elevation` (-90 to +90)
- `north_rotation` is applied to the solar azimuth before shadow projection — NOT to
  geometry (per ADR-003)
- No shapely/numpy in deps — only stdlib `math` for geometry

## Available dependencies (pyproject.toml)

- `cosalette>=0.1.7`, `astral>=3.2`, `pydantic>=2.10.0`, `pyyaml>=6.0`
- Optional: `cairosvg>=2.7` (PNG), `aiohttp>=3.9` (HTTP)
- Python 3.14+ required

## ADR decisions

- ADR-000: GPL-3.0-or-later + clean-room reimplementation, attribution header required
  in all source files
- ADR-001: Cosalette telemetry app, `@app.telemetry()` with `Every(seconds=360)`
- ADR-002: `astral` library for solar position computation
- ADR-003: YAML/JSON + SVG sidecar for geometry; north_rotation on azimuth not geometry
- ADR-004: Filesystem + MQTT + optional HTTP output; shadow.svg always generated

## Test patterns

- `@pytest.mark.unit` on every test class
- AAA pattern with `# Arrange`, `# Act`, `# Assert` comments
- Module docstring lists ISTQB techniques used
- Class docstring names specific technique
- `pytest.approx()` for float comparisons
- `tmp_path` fixture for file-based tests
- Named fixtures for complex setup (e.g. `berlin_summer_solstice_noon`)
- Coverage threshold: 80% (`fail_under = 80`)
- Strict markers (`--strict-markers`)
- asyncio_mode = "auto" (no `@pytest.mark.asyncio` needed)

## License header template (all source files)

```
# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# ...
# Inspired by the sun position and shadow visualization concept shared by pmpkk (Patrick)
# on the OpenHAB community forum:
# https://community.openhab.org/t/show-current-sun-position-and-shadow-of-house-generate-svg/34764
```

Note: ADR-000 requires attribution to pmpkk specifically in shadow.py header.

## Task commands

`task suncast:test:unit` — run unit tests `task suncast:lint`, `task suncast:typecheck`,
`task suncast:check` — quality gates `task suncast:test` — all tests with coverage
