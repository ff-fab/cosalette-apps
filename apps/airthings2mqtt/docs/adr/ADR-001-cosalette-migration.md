# ADR-001: Migrate to cosalette Framework

## Status

Accepted **Date:** 2026-03-25

## Context

The airthings2mqtt application reads Airthings Wave air quality sensors over BLE and
publishes temperature, humidity, and radon data to MQTT. Before adopting cosalette, a
greenfield implementation would have required manual MQTT connection management, polling
loops, error handling, and health reporting --- all boilerplate that the cosalette
framework already provides.

Key concerns that drove the decision:

- **BLE reliability** --- Bluetooth Low Energy connections are inherently unreliable.
  Each polling cycle involves a full connect-read-disconnect cycle that can fail due to
  range, interference, or device sleep states. The framework must isolate these failures
  without crashing the process.
- **Long polling intervals** --- Airthings Wave sensors update readings every ~5 minutes
  internally, making the default polling interval 1500 seconds (25 minutes). The
  framework must support shutdown-aware sleep over long intervals.
- **Operational visibility** --- the sensor runs unattended, typically on a headless
  Raspberry Pi. Heartbeats, per-device availability, and Last Will and Testament (LWT)
  are essential for detecting silent failures via MQTT alone.
- **Adapter testability** --- the BLE adapter (Bleak) cannot run in CI. A clean
  port/adapter boundary enables testing the entire application logic without hardware.

## Decision

Build airthings2mqtt on the **cosalette** IoT-to-MQTT framework (v0.1.7+).

cosalette provides:

- `@app.telemetry()` for periodic polling with automatic publish and error isolation
- Deferred interval resolution (`interval=lambda s: s.poll_interval`) to avoid
  accessing settings at module level (ADR-020 pattern)
- Automatic MQTT connection management with reconnect
- Built-in health reporting: heartbeats, per-device availability, LWT
- Pydantic-based settings with env / `.env` / CLI layering
- Dependency injection via type annotations
- Adapter registration with dry-run alternatives

## Decision Drivers

- **Error isolation** --- BLE failures must not crash the polling loop. cosalette's
  telemetry decorator catches exceptions, logs them, publishes to the error topic, and
  continues the next poll cycle automatically.
- **Testability** --- the Ports & Adapters pattern lets us swap the Bleak adapter for a
  `FakeAirthingsReader` in tests, enabling full coverage without BLE hardware.
- **Shutdown awareness** --- `@app.telemetry` uses `ctx.sleep()` internally, which
  returns early on SIGTERM/SIGINT. Critical for Docker deployments where graceful
  shutdown must complete within the stop timeout.
- **Configuration** --- Pydantic settings with the `AIRTHINGS2MQTT_` prefix support
  Docker-native `.env` files and environment variable overrides.
- **Operational visibility** --- heartbeats and LWT are free from cosalette, essential
  for unattended Raspberry Pi deployments.

## Considered Options

1. **cosalette framework** --- purpose-built for IoT-to-MQTT bridges.
2. **Manual implementation** --- custom async loop with aiomqtt directly.
3. **Home Assistant add-on** --- rewrite as an HA integration.

## Decision Matrix

| Criterion              | cosalette | Manual | HA Add-on |
| ---------------------- | --------- | ------ | --------- |
| BLE error isolation    | 5         | 3      | 4         |
| Testability            | 5         | 3      | 3         |
| Operational visibility | 5         | 2      | 4         |
| Migration effort       | 5         | 4      | 2         |
| Deployment flexibility | 5         | 5      | 2         |
| Maintenance burden     | 5         | 3      | 3         |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- **Ports-and-adapters architecture** --- domain types (`AirthingsReading`,
  `AirthingsReaderPort`) have zero I/O dependencies. The Bleak adapter is a thin wrapper
  that translates GATT characteristics to domain types.
- **Comprehensive test suite** --- unit tests cover the telemetry handler, adapter error
  translation, and settings validation without BLE hardware.
- **Single telemetry device** --- the `@app.telemetry("airthings", interval=...)` pattern
  maps naturally to the single-sensor-per-instance deployment model.
- **Deferred interval** --- `interval=_poll_interval` resolves from settings after
  construction, allowing `--help` and `--version` to work without required env vars.
- **Automatic health reporting** --- heartbeats, per-device availability, and LWT come
  free from cosalette.
- **Docker-ready** --- Pydantic settings + `.env` files work naturally with
  `docker compose`. The `network_mode: host` configuration provides D-Bus access for BLE.

### Negative

- **Framework dependency** --- the application depends on cosalette's lifecycle and
  conventions. API changes in cosalette require migration work.
- **Python 3.14+ requirement** --- cosalette requires Python 3.14+, limiting deployment
  to systems with recent Python.
- **Single-sensor model** --- each instance monitors one Airthings device. Multi-sensor
  setups require multiple container instances or a future enhancement using
  `app.add_telemetry()` in a loop.

_2026-03-25_
