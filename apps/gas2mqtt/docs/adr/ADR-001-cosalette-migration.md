# ADR-001: Migrate to cosalette Framework

## Status

Accepted **Date:** 2026-02-22

## Context

The gas2mqtt application originated as a single 185-line Python script (`hmc5883.py`)
using direct `smbus`, `paho-mqtt`, and `argparse` calls.  While functional, this
monolithic design carried significant maintenance and reliability risks:

- **No test coverage** — the script was untestable because I2C hardware access, MQTT
  publishing, and business logic were tightly coupled in a single loop.
- **Hardcoded configuration** — MQTT credentials and sensor parameters were embedded in
  source.  Changing anything required editing and redeploying the script.
- **No error isolation** — an exception in the polling loop would crash the entire
  process with no notification.
- **No health reporting** — no heartbeats, no Last Will and Testament (LWT), no
  per-device availability.  Silent failures were common.
- **Global mutable state** — the I2C bus handle, MQTT client, and counter state were all
  module-level globals, making the code fragile and order-dependent.
- **Single sensor assumption** — adding a second sensor would require duplicating most
  of the script.

## Decision

Migrate gas2mqtt to the **cosalette** IoT-to-MQTT framework (v0.1.0+).

cosalette provides a declarative application model for IoT bridges:

- `@app.device()` for full-lifecycle coroutines with shutdown awareness
- `@app.telemetry()` for periodic polling devices
- `@app.command()` for inbound MQTT command handlers
- Automatic MQTT connection management with reconnect
- Built-in health reporting: heartbeats, per-device availability, LWT
- Automatic error isolation and error topics
- Pydantic-based settings with env / `.env` / CLI layering
- Dependency injection via type annotations
- Adapter registration with dry-run alternatives

## Decision Drivers

- **Testability first** — the primary goal was achieving meaningful test coverage.
  cosalette's DI system and adapter pattern make every component independently testable.
- **Operational visibility** — heartbeats, availability, and error topics are
  table-stakes for unattended IoT deployments.
- **Configuration flexibility** — moving to Pydantic settings eliminates hardcoded
  values and supports Docker-native `.env` files.
- **Reduced boilerplate** — cosalette handles MQTT lifecycle, signal handling, and
  graceful shutdown, eliminating ~50 lines of manual plumbing.

## Considered Options

1. **cosalette framework** — purpose-built for IoT-to-MQTT bridges.
2. **Manual refactor** — restructure the script into modules without a framework.
3. **Home Assistant add-on** — rewrite as an HA integration.

## Decision Matrix

| Criterion | cosalette | Manual Refactor | HA Add-on |
| --- | --- | --- | --- |
| Testability | 5 | 4 | 3 |
| Operational visibility | 5 | 2 | 4 |
| Migration effort | 4 | 3 | 2 |
| Deployment flexibility | 5 | 5 | 2 |
| Maintenance burden | 5 | 3 | 3 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- **101 tests** (94 unit + 7 integration) covering all domain logic, devices, adapters,
  and app wiring — up from zero.
- **Ports-and-adapters architecture** — domain logic (`schmitt.py`, `ewma.py`,
  `consumption.py`) has zero I/O dependencies.
- **12 focused modules** replacing one monolithic script, each with a single
  responsibility.
- **Declarative device model** — `@app.device()` coroutines with `DeviceContext`
  injection replace manual MQTT plumbing.
- **Automatic health reporting** — heartbeats, per-device availability, and LWT come
  free from cosalette.
- **Docker-ready deployment** — Pydantic settings + `.env` files work naturally with
  `docker compose`.
- **Dry-run mode** — `FakeMagnetometer` adapter enables running without hardware for
  development and CI.

### Negative

- **Framework dependency** — the application now depends on cosalette's lifecycle and
  conventions.  If cosalette's API changes, migration work is needed.
- **Python 3.14+ requirement** — cosalette requires Python 3.14+, limiting deployment
  to systems with recent Python.
- **Learning curve** — contributors need to understand cosalette's device model and DI
  system in addition to the domain logic.

_2026-02-22_
