# ADR-005: Configuration and Settings

## Status

Accepted **Date:** 2026-02-27

## Context

The vito2mqtt bridge requires several categories of runtime configuration: MQTT broker
connection details, serial port path and baud rate, per-domain polling intervals, and
device identity for MQTT topics. The configuration approach must support environment
variables (for 12-factor app compliance), `.env` files (for Docker Compose workflows),
and provide sensible defaults so users only need to configure what differs from the
common case.

The chosen application framework, cosalette (see ADR-001), provides a `Settings` base
class built on pydantic-settings, establishing a convention for how IoT bridge
applications handle configuration. Each polling interval corresponds to one domain
entity defined in ADR-002's topic layout.

## Decision

Use a **`cosalette.Settings` subclass** (`Vito2MqttSettings`) with pydantic-settings
because it provides type-safe validation, environment variable binding with a consistent
prefix, `.env` file support, and aligns with the framework's configuration conventions.

**Environment variable prefix:** `VITO2MQTT_`

**Default polling intervals:**

| Domain             | Default interval | Rationale                               |
| ------------------ | ---------------- | --------------------------------------- |
| outdoor            | 300s (5 min)     | Outdoor temp changes slowly             |
| hot_water          | 300s (5 min)     | DHW state changes are infrequent        |
| burner             | 300s (5 min)     | Burner stats change slowly              |
| heating_radiator   | 300s (5 min)     | Circuit state changes gradually         |
| heating_floor      | 300s (5 min)     | Floor heating is inherently slow        |
| system             | 3600s (1 hr)     | System info is near-static              |
| diagnosis          | 300s (5 min)     | Error states should be caught promptly  |

**Application-specific settings:**

| Setting            | Type | Default          | Notes                             |
| ------------------ | ---- | ---------------- | --------------------------------- |
| `serial_port`      | str  | _(required)_     | e.g., `/dev/ttyUSB0`              |
| `serial_baud_rate` | int  | 4800             | P300 protocol standard baud rate  |
| `device_id`        | str  | `vitodens200w`   | Used in MQTT topic construction   |

MQTT settings (broker host, port, credentials, TLS) are inherited from the
`cosalette.Settings` base class.

## Decision Drivers

- 12-factor app configuration via environment variables
- Docker-friendly deployment with `.env` file support
- Type-safe validation catching misconfiguration at startup, not at runtime
- cosalette framework alignment using the standard `Settings` subclass pattern
- Sensible defaults that minimize required configuration for the common case
- Per-domain polling intervals allowing users to tune polling frequency based on how
  quickly each subsystem's data changes

## Considered Options

- **Option 1: cosalette.Settings subclass** — pydantic-settings with env var binding and
  `.env` support
- **Option 2: YAML/TOML config file** — traditional configuration file parsed at startup
- **Option 3: CLI arguments** — argparse or click-based command-line configuration

## Decision Matrix

| Criterion            | cosalette.Settings | YAML/TOML config | CLI arguments |
| -------------------- | ------------------ | ---------------- | ------------- |
| 12-factor compliance | 5                  | 2                | 3             |
| Docker integration   | 5                  | 3                | 2             |
| Type safety          | 5                  | 3                | 3             |
| Framework alignment  | 5                  | 2                | 1             |
| User experience      | 4                  | 4                | 3             |
| **Total**            | **24**             | **14**           | **12**        |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Misconfiguration (wrong types, missing required fields) is caught immediately at
  application startup with clear pydantic validation errors
- Environment variable prefix `VITO2MQTT_` provides a clean namespace that avoids
  collisions with other applications in the same environment
- Per-domain polling intervals allow users to tune the balance between data freshness
  and serial bus load for their specific use case
- `.env` file support enables a simple `docker-compose.yml` workflow where all
  configuration lives in a single `.env` file alongside the compose file
- Inheriting MQTT settings from the cosalette base class means broker configuration
  follows documented framework conventions, reducing project-specific documentation needs

### Negative

- Environment variable names for nested settings (e.g., polling intervals per domain)
  can become verbose: `VITO2MQTT_POLLING_OUTDOOR=300`
- No support for runtime configuration changes — modifying polling intervals requires
  restarting the application
- pydantic-settings dependency adds to the dependency tree, though it is already a
  transitive dependency via cosalette
- Users accustomed to YAML/TOML configuration files may find environment-variable-only
  configuration less intuitive for complex settings

_2026-02-27_
