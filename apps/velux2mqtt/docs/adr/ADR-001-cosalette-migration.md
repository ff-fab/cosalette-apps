# ADR-001: Migrate to cosalette Framework

## Status

Accepted **Date:** 2026-03-24 | Amended **Date:** 2026-05-14

## Context

The velux2mqtt application controls Velux covers (blinds and windows) by simulating
button presses on KLF 050 radio remotes via GPIO-driven M74HC4066 analog switches. The
original implementation was a standalone script with manual MQTT handling, GPIO setup,
and an ad-hoc command loop.

Key problems with the pre-cosalette design:

- **Tight coupling** --- GPIO access, MQTT publishing, position tracking, and command
  parsing were interleaved in a single loop. Testing any component required the entire
  stack.
- **No health reporting** --- no heartbeats, no Last Will and Testament (LWT), no
  per-device availability. Silent failures on a headless Raspberry Pi were undetectable
  without SSH access.
- **Hardcoded configuration** --- GPIO pins, travel durations, and MQTT credentials
  required code changes to modify. No support for `.env` files or Docker deployments.
- **No error isolation** --- a GPIO exception would crash the entire process, potentially
  leaving a cover mid-travel with no stop command sent.
- **Multi-cover complexity** --- supporting multiple covers (e.g. a blind and a window
  on the same Pi) required duplicating the command loop and state management.

## Decision

Migrate velux2mqtt to the **cosalette** IoT-to-MQTT framework (v0.1.0+).

cosalette provides a declarative application model for IoT bridges:

- `@app.device()` for full-lifecycle coroutines with shutdown awareness
- Automatic MQTT connection management with reconnect
- Built-in health reporting: heartbeats, per-device availability, LWT
- Automatic error isolation and error topics
- Pydantic-based settings with env / `.env` / CLI layering
- Dependency injection via type annotations
- Adapter registration with dry-run alternatives

velux2mqtt uses `app.add_device()` (the imperative form) to register one device per
configured cover, since covers are defined in settings rather than being static
decorators.

## Decision Drivers

- **Testability** --- the primary goal was enabling comprehensive test coverage.
  cosalette's DI system and adapter pattern make every component independently testable.
  The `FakeGpio` adapter allows testing GPIO sequences without hardware.
- **Multi-cover support** --- each cover needs independent state (position tracker, drift
  compensator, calibration state machine). cosalette's device model naturally supports
  this via `app.add_device()` in a loop, each with its own `DeviceContext`.
- **Operational visibility** --- heartbeats, per-device availability, and LWT are
  essential for unattended Raspberry Pi deployments where the only interface is MQTT.
- **Configuration flexibility** --- Pydantic settings eliminate hardcoded values and
  support Docker-native `.env` files. The complex cover configuration (JSON list of
  objects) validates at startup with clear error messages.
- **Graceful shutdown** --- the cover device must send a stop command to the GPIO when
  shutting down to avoid leaving a cover mid-travel. cosalette's `ctx.shutdown_requested`
  and `ctx.sleep()` make this straightforward.

## Considered Options

1. **cosalette framework** --- purpose-built for IoT-to-MQTT bridges.
2. **Manual refactor** --- restructure into modules without a framework.
3. **Home Assistant add-on** --- rewrite as an HA integration.

## Decision Matrix

| Criterion              | cosalette | Manual Refactor | HA Add-on |
| ---------------------- | --------- | --------------- | --------- |
| Testability            | 5         | 4               | 3         |
| Multi-cover support    | 5         | 3               | 4         |
| Operational visibility | 5         | 2               | 4         |
| Migration effort       | 4         | 3               | 2         |
| Deployment flexibility | 5         | 5               | 2         |
| Maintenance burden     | 5         | 3               | 3         |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- **Ports-and-adapters architecture** --- domain logic (`position.py`, `command.py`,
  `drift.py`, `calibration.py`) has zero I/O dependencies.
- **Comprehensive test suite** --- unit tests cover all domain modules, adapters, ports,
  and settings; integration tests verify the full app wiring and calibration end-to-end.
- **Multi-cover by configuration** --- adding a second cover requires only a JSON config
  entry, not code changes.
- **Closure-based device factory** --- `make_cover()` returns an async callable per cover,
  capturing configuration without global state.
- **Automatic health reporting** --- heartbeats, per-device availability, and LWT come
  free from cosalette.
- **Docker-ready deployment** --- Pydantic settings + `.env` files work naturally with
  `docker compose`.
- **Dry-run mode** --- `FakeGpio` adapter enables running without hardware for
  development and CI.

### Negative

- **Framework dependency** --- the application depends on cosalette's lifecycle and
  conventions. If cosalette's API changes, migration work is needed.
- **Python 3.14+ requirement** --- cosalette requires Python 3.14+, limiting deployment
  to systems with recent Python.
- **Learning curve** --- contributors need to understand cosalette's device model and DI
  system in addition to the domain logic.

## Amendment (2026-05-14) — Corrective

**Rationale:** cosalette 0.4 exposes dict-name device registration via @app.device(name=callable), so configured covers can now be expanded declaratively while preserving one DeviceContext and independent runtime state per cover.

> **Justification for amendment (not supersession):** Supersession is not warranted because the primary decision to use cosalette remains unchanged; the impact is confined to the velux2mqtt composition root, cover handler entry point, tests, and documentation, with no MQTT contract or domain model migration.

### Revised Decision

Use cosalette dict-name @app.device registration for configured Velux covers because it keeps one device per cover while removing the imperative on_configure/add_device loop from the composition root.

```python
def _cover_map(settings: cosalette.Settings) -> dict[str, CoverConfig]:
    if not isinstance(settings, Velux2MqttSettings):
        raise TypeError(f"Expected Velux2MqttSettings, got {type(settings).__name__}")
    return {cover.name: cover for cover in settings.covers}


@app.device(name=_cover_map, summary="Velux cover: open/close/stop control")
async def cover(
    ctx: cosalette.DeviceContext,
    cover_cfg: CoverConfig,
    settings: Velux2MqttSettings,
):
    async for event in cover_device(ctx, cover_cfg, settings):
        yield event
```

### Additional Sub-Decision: Keep make_cover() as a compatibility wrapper

The application registers the top-level `cover_device()` through `@app.device(name=_cover_map)`. `make_cover()` remains as a small wrapper for focused unit tests and external callers that need a pre-bound device function.

### Additional Positive Consequences

- The composition root now uses cosalette's declarative multi-device API while preserving one independent runtime device per configured cover.
- Direct composition tests can assert the name-mapping registration without duplicating the production add_device loop.

### Additional Negative Consequences

- Per-cover summary text is now generic at registration time because dict-name expansion does not provide a per-expanded-device summary hook.
- The top-level handler must expose CoverConfig and Velux2MqttSettings as explicit dependencies instead of relying solely on closure capture.

## Amendment (2026-05-14) — Corrective

**Rationale:** The first 2026-05-14 amendment correctly moved configured covers to cosalette dict-name device registration, but its code example retained a local decorator-facing wrapper in main.py. The final implementation registers cover_device directly with app.device(...)(cover_device) and places the device contract in declarative registration metadata.

> **Justification for amendment (not supersession):** Supersession is not warranted because the primary decision and the earlier corrective amendment still stand: velux2mqtt uses cosalette dict-name device expansion. The impact is confined to clarifying the composition-root registration form and documentation; MQTT topics, domain models, and runtime device behavior remain unchanged.

### Revised Decision

Register configured Velux covers with cosalette dict-name device expansion by applying app.device(...)(cover_device) directly. Use registration metadata (summary, behavior, effects) in main.py to declare the device contract while keeping the command-loop implementation in devices/cover.py.

```python
def _cover_map(settings: cosalette.Settings) -> dict[str, CoverConfig]:
    if not isinstance(settings, Velux2MqttSettings):
        raise TypeError(f"Expected Velux2MqttSettings, got {type(settings).__name__}")
    return {cover.name: cover for cover in settings.covers}


app.device(
    name=_cover_map,
    summary="Velux cover: GPIO-driven open/close/stop/position control",
    behavior=[
        "Startup homing to a known endpoint for reliable position reference",
        "Open/close/stop commands via GPIO button presses on KLF 050 remote",
        "Position targeting (0-100%) with time-based position tracking",
        "Calibration sub-entity (start/go/mark/cancel phases)",
    ],
    effects=[
        "Presses GPIO pins (up/stop/down) via GpioSwitchPort",
        "Publishes cover position state to MQTT",
    ],
)(cover_device)
```

### Additional Sub-Decision: Keep make_cover() as a pre-binding helper, not the app registration path

The application registers `cover_device` directly. `make_cover()` remains available for focused tests and external callers that need a single-argument cosalette-compatible device callable with `CoverConfig` and `Velux2MqttSettings` pre-bound.

### Additional Positive Consequences

- main.py now reads declaratively: it exposes configured device expansion plus summary, behavior, and effects metadata without a pass-through wrapper.
- The registered function identity is the runtime implementation (`cover_device`), so composition tests and manifests point at the actual device handler.

### Additional Negative Consequences

- The registration uses call-form decoration (`app.device(...)(cover_device)`) instead of `@app.device` syntax, because Python decorator syntax requires defining a local wrapper.
