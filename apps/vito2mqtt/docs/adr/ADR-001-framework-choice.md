# ADR-001: Framework Choice — cosalette

## Status

Accepted **Date:** 2026-02-27

## Context

vito2mqtt is an IoT-to-MQTT bridge daemon for a Viessmann Vitodens 200-W boiler. The
application must publish telemetry readings to an MQTT broker at configurable intervals
and accept inbound commands via MQTT to modify boiler parameters. This requires robust
MQTT lifecycle management (connection, reconnection, graceful shutdown), a clean
application structure for registering multiple device signals, type-safe configuration,
and solid testing infrastructure.

Choosing the right application framework determines how much boilerplate the project
carries, how testable the result is, and how quickly contributors can understand the
codebase.

## Decision

Use **cosalette** (v0.1.5+) as the application framework because it provides a
purpose-built composition root for IoT-to-MQTT bridges with decorator-based device
registration, async MQTT lifecycle management, hexagonal architecture support via PEP 544
Protocol ports, and integrated testing infrastructure.

## Decision Drivers

- Composition root pattern for clean application assembly
- Async MQTT lifecycle management (broker connection, reconnection, graceful shutdown)
- Decorator-based device API (`@app.telemetry`, `@app.command`, `@app.device`)
- Built-in hexagonal architecture support via PEP 544 Protocol ports
- Built-in health and availability telemetry
- Testing infrastructure (`AppHarness`, MQTT fixtures)
- pydantic-settings integration for type-safe configuration

## Considered Options

- **Option 1: cosalette** — purpose-built IoT-to-MQTT application framework
- **Option 2: Raw paho-mqtt** — direct MQTT client library with manual lifecycle
- **Option 3: FastAPI + mqtt-client** — web framework with MQTT bolted on as a side
  channel
- **Option 4: Custom framework** — bespoke application skeleton built from scratch

## Decision Matrix

| Criterion              | cosalette | Raw paho-mqtt | FastAPI + mqtt | Custom |
| ---------------------- | --------- | ------------- | -------------- | ------ |
| MQTT lifecycle mgmt    | 5         | 3             | 2              | 3      |
| Device abstraction     | 5         | 1             | 1              | 4      |
| Testing support        | 5         | 2             | 3              | 2      |
| Configuration mgmt     | 5         | 2             | 4              | 2      |
| Code maintainability   | 5         | 2             | 3              | 3      |
| Learning curve         | 3         | 4             | 3              | 5      |
| **Total**              | **28**    | **14**        | **16**         | **19** |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Idiomatic device registration via decorators eliminates boilerplate for adding new
  telemetry signals or commands
- Built-in `AppHarness` and MQTT fixtures enable integration testing without a real
  broker, accelerating TDD cycles
- Standard pydantic-settings configuration pattern provides type-safe, validated settings
  with environment variable and `.env` file support out of the box
- Framework handles MQTT connection lifecycle (connect, reconnect, graceful shutdown),
  removing a major source of subtle bugs
- Hexagonal architecture support via Protocol ports is a first-class framework feature,
  not an afterthought

### Negative

- Framework dependency on a pre-1.0 release (v0.1.x) means the API surface may evolve
  with breaking changes
- Smaller community compared to general-purpose frameworks means fewer Stack Overflow
  answers and third-party tutorials
- Framework-specific patterns (composition root, decorators, harness) require upfront
  learning investment for new contributors
- Tight coupling to cosalette conventions limits the ability to swap frameworks later
  without significant refactoring

_2026-02-27_
