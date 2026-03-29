# ADR-002: Solar Position Computation

## Status

Accepted **Date:** 2026-03-29

## Context

An existing proof-of-concept receives solar position data (azimuth, elevation,
sunrise/sunset azimuths, hourly azimuths) from OpenHAB's astro binding via HTTP query
parameters. This creates a hard dependency on OpenHAB and prevents the app from running
autonomously.

The app needs to compute solar positions internally given only GPS coordinates
(latitude, longitude), timezone, and current time.

## Decision

Use the **`astral`** library (BSD-2-Clause license, pure Python, no compiled
dependencies) for all solar position calculations.

The app will compute on each cycle:

- Current sun azimuth and elevation
- Sunrise and sunset times and their azimuths
- Hourly azimuths for the current day (00:00–23:00)

### Configuration

Required settings:

- `latitude: float` — GPS latitude of the location
- `longitude: float` — GPS longitude of the location
- `timezone: str` — IANA timezone identifier (e.g., `Europe/Berlin`)

These are provided via environment variables following cosalette conventions:
`SUNCAST_LATITUDE`, `SUNCAST_LONGITUDE`, `SUNCAST_TIMEZONE`.

### Integration with Cosalette

Solar computation is injected via cosalette's `ClockPort` for time (enabling
deterministic testing with `FakeClock`) and `Settings` for GPS coordinates.

## Decision Drivers

- Eliminate external dependency on OpenHAB astro binding
- Pure Python with no compiled extensions (simplifies Docker builds)
- Well-maintained library with accurate astronomical algorithms
- BSD-2-Clause compatible with GPL-3.0-or-later

## Considered Options

1. **`astral`** — BSD-2-Clause, pure Python, actively maintained, covers all needed
   calculations
2. **`ephem` (PyEphem)** — LGPL, C extension, very accurate, but heavier
3. **`pysolar`** — GPL-3.0, pure Python, but less actively maintained
4. **Custom implementation** — full control, but significant effort for no benefit

## Decision Matrix

| Criterion         | astral | ephem | pysolar | Custom |
| ----------------- | ------ | ----- | ------- | ------ |
| License compat.   | 5      | 4     | 5       | 5      |
| Ease of use       | 5      | 3     | 4       | 2      |
| Docker simplicity | 5      | 2     | 5       | 5      |
| Accuracy          | 4      | 5     | 4       | 2      |
| Maintenance       | 5      | 4     | 2       | 1      |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Single `pip install astral` replaces entire OpenHAB astro binding dependency chain
- Pure Python — no build tools needed in Docker image
- ClockPort injection makes all time-dependent logic fully testable
- BSD-2-Clause is compatible with our GPL-3.0-or-later license

### Negative

- Slightly less accurate than ephemeris-based solutions (negligible for shadow
  visualization where ~0.1 degree precision is sufficient)

_2026-03-29_
