# ADR-001: Application Framework

## Status

Accepted **Date:** 2026-03-04

## Context

jeelink2mqtt is a daemon that bridges JeeLink LaCrosse temperature/humidity sensors to
an MQTT broker. The application requires:

- **MQTT lifecycle management** — connection, reconnection, graceful disconnect, LWT
- **Structured logging** — JSON-formatted logs for observability
- **Health reporting** — device availability published to MQTT
- **Configuration** — environment variables and CLI flags (12-factor)
- **Graceful shutdown** — clean teardown of serial and MQTT resources on SIGTERM/SIGINT
- **Error isolation** — one misbehaving sensor must not crash the daemon
- **Testing support** — run the full application logic without hardware or a live broker
- **Dry-run mode** — develop and debug without physical JeeLink hardware

The framework choice is foundational — it shapes the entire application architecture,
testing strategy, and developer experience.

## Decision

Use **cosalette** as the application framework because it provides all required
infrastructure out of the box while its hexagonal architecture (ports and adapters)
enables clean hardware abstraction and testing without mocks.

## Decision Drivers

- MQTT lifecycle management (connect, reconnect, LWT, graceful shutdown)
- Device health and availability reporting
- Testability via port/adapter pattern (no hardware needed)
- Configuration from environment variables (pydantic-settings)
- Structured logging with configurable levels
- Development velocity (convention over configuration)
- Dry-run mode for hardware-less development
- Error isolation per device

## Considered Options

1. **cosalette** — opinionated Python framework for IoT-to-MQTT bridges. Provides MQTT
   lifecycle, device archetypes (`@app.device`, `@app.telemetry`, `@app.command`),
   hexagonal architecture (ports/adapters), pydantic-settings integration, structured
   logging, health/availability reporting, error isolation, CLI (`--dry-run`,
   `--log-level`), and a testing module.

2. **Raw paho-mqtt + asyncio** — build a custom daemon using paho-mqtt for the MQTT
   client, a hand-coded asyncio event loop, manual reconnection logic, custom
   configuration loading, and custom logging setup.

3. **Home Assistant Add-on** — build as a Home Assistant add-on, leveraging HA's MQTT
   integration and supervisor infrastructure directly.

## Decision Matrix

| Criterion              | cosalette | paho-mqtt + asyncio | HA Add-on |
| ---------------------- | --------- | ------------------- | --------- |
| MQTT lifecycle         | 5         | 3                   | 4         |
| Health reporting       | 5         | 1                   | 3         |
| Testability            | 5         | 2                   | 2         |
| Configuration          | 5         | 2                   | 3         |
| Structured logging     | 5         | 2                   | 3         |
| Development velocity   | 5         | 2                   | 3         |
| Dry-run mode           | 5         | 1                   | 1         |
| Error isolation        | 5         | 2                   | 3         |
| Deployment flexibility | 5         | 5                   | 1         |
| **Total**              | **45**    | **20**              | **23**    |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- All MQTT plumbing (connect, reconnect, LWT, graceful shutdown) is handled by the
  framework — zero boilerplate
- Device archetypes (`@app.device` for push-based, `@app.telemetry` for polling)
  provide clear patterns for JeeLink integration
- Hexagonal architecture enforces separation between domain logic and infrastructure,
  making the codebase testable from day one
- Built-in `--dry-run` flag enables development without hardware
- pydantic-settings integration provides validated, typed configuration with
  environment variable support
- Error isolation ensures a single sensor failure cannot crash the daemon
- Testing module allows full integration tests without a live MQTT broker

### Negative

- Couples the project to a specific framework — migration would require rewriting
  application wiring
- Team must learn cosalette's conventions and device archetypes
- Framework updates may introduce breaking changes that require adaptation

_2026-03-04_
