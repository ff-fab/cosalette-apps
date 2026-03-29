# ADR-001: Cosalette App Architecture

## Status

Accepted **Date:** 2026-03-29

## Context

The application's purpose is to provide a shadow visualization service that generates
SVG images showing the sun position and shadow cast by a house.

The service shall be a self-contained cosalette app (`suncast`) that computes solar
positions internally, generates shadow visualizations, and publishes results via MQTT.

## Decision

Build `suncast` as a cosalette framework app using `@app.telemetry()` with
`Every(seconds=360)` publish strategy. The app will:

1. Compute sun position (azimuth, elevation) and daily astronomical data internally
   using GPS coordinates and system time.
2. Generate shadow SVG (and optionally PNG) from building geometry and sun position.
3. Publish results via MQTT and write to a configurable filesystem path.
4. Optionally serve images via an embedded HTTP server (for non-Docker deployments).

## Decision Drivers

- Self-reliance: eliminate dependency on OpenHAB astro binding
- Multi-consumer: support both OpenHAB and Home Assistant via MQTT
- Testability: cosalette's `FakeClock` and `MockMqttClient` enable deterministic tests
- Consistency: all apps in this monorepo use cosalette

## Considered Options

1. **Implement as FastAPI service** — HTTP-based API called by OpenHAB or HomeAssistant
2. **Cosalette telemetry device** — periodic autonomous computation + MQTT publish
3. **Cosalette command device** — MQTT-triggered on-demand generation

## Decision Matrix

| Criterion            | FastAPI | Telemetry device | Command device |
| -------------------- | ------- | ---------------- | -------------- |
| Self-reliance        | 1       | 5                | 3              |
| Multi-consumer       | 2       | 5                | 4              |
| Testability          | 2       | 5                | 5              |
| Simplicity           | 3       | 4                | 3              |
| Monorepo consistency | 1       | 5                | 5              |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- App runs autonomously with only GPS coordinates as configuration
- Both OpenHAB and Home Assistant can consume shadow images via MQTT
- Deterministic testing with FakeClock for any date/time/location
- Consistent with all other apps in the monorepo

### Negative

- Requires reimplementation of solar position math (mitigated by `astral` library)
- Requires clean-room reimplementation of shadow geometry (see ADR-002)

_2026-03-29_
