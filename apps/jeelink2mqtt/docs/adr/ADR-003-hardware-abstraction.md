# ADR-003: Hardware Abstraction

## Status

Accepted **Date:** 2026-03-04

## Context

The JeeLink USB receiver communicates via serial and uses the LaCrosse protocol to
receive temperature/humidity readings from wireless sensors. The `pylacrosse` Python
library handles serial communication, LaCrosse protocol frame parsing, and JeeLink
device control (LED toggling, scan start/stop).

The application needs to:

- **Run without hardware** — both for automated tests and `--dry-run` development
- **Avoid re-implementing protocol parsing** — the LaCrosse protocol is well-handled by
  `pylacrosse`; reimplementation risks correctness bugs
- **Support lazy imports** — `pylacrosse` (and its `pyserial` dependency) should not be
  required at import time on development machines
- **Maintain single responsibility** — domain logic (sensor mapping, health tracking)
  must not depend on serial communication details

The JeeLink receiver is **push-based**: sensors transmit asynchronously and the receiver
emits frames as they arrive. This characteristic determines which cosalette device
archetype to use.

## Decision

Use a **hexagonal port wrapping pylacrosse** — define a `JeeLinkPort` Protocol
(PEP 544) that abstracts the receiver interface, with a production adapter wrapping
`pylacrosse` and a fake adapter for tests and dry-run mode.

## Decision Drivers

- Testability without hardware or mocks
- Dry-run support for development without a physical JeeLink
- Protocol correctness (no re-implementation risk)
- Lazy imports (pylacrosse/pyserial not required at import time)
- Single responsibility (domain logic independent of serial details)
- Alignment with cosalette's hexagonal architecture (ADR-001)

## Considered Options

1. **Hexagonal port wrapping pylacrosse** — define a `JeeLinkPort` Protocol (PEP 544)
   abstracting the receiver. Production adapter wraps `pylacrosse` with lazy import.
   Fake adapter produces configurable synthetic readings for tests and dry-run.

2. **Direct pylacrosse usage** — call `pylacrosse` directly in device code. Use
   `unittest.mock.patch` to substitute it in tests.

3. **Raw pyserial with custom protocol parsing** — skip `pylacrosse` entirely. Implement
   LaCrosse frame parsing from scratch using `pyserial` directly.

## Decision Matrix

| Criterion                | Hexagonal port | Direct pylacrosse | Raw pyserial |
| ------------------------ | -------------- | ----------------- | ------------ |
| Testability              | 5              | 2                 | 2            |
| Dry-run support          | 5              | 1                 | 1            |
| Protocol correctness     | 5              | 5                 | 2            |
| Lazy imports             | 5              | 2                 | 2            |
| Single responsibility    | 5              | 2                 | 1            |
| Implementation effort    | 3              | 5                 | 1            |
| Framework alignment      | 5              | 2                 | 2            |
| **Total**                | **33**         | **19**            | **11**       |

_Scale: 1 (poor) to 5 (excellent)_

## Design Notes

### Device Archetype

The JeeLink's push-based nature maps to cosalette's `@app.device()` archetype — a
long-running coroutine that owns its event loop and yields readings as they arrive. This
is distinct from `@app.telemetry()`, which is framework-controlled polling on a fixed
interval.

### Port Protocol

```python
class JeeLinkPort(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def readings(self) -> AsyncIterator[SensorReading]: ...
```

### Adapters

- **`PyLaCrosseAdapter`** — production adapter wrapping `pylacrosse`. Uses lazy import
  so that `pylacrosse` and `pyserial` are only loaded when actually needed.
- **`FakeJeeLinkAdapter`** — produces configurable synthetic readings. Used by tests
  (deterministic sequences) and `--dry-run` mode (random realistic values).

## Consequences

### Positive

- Tests run without hardware, serial ports, or mock patching — just inject the fake
  adapter
- Dry-run mode works out of the box by selecting the fake adapter
- `pylacrosse` handles all protocol complexity — no risk of parsing bugs
- Lazy import means developers can run tests and dry-run without installing
  `pylacrosse` or `pyserial`
- Clean separation: domain logic depends only on the `JeeLinkPort` Protocol, never on
  serial implementation details
- Aligns naturally with cosalette's port/adapter registration

### Negative

- Thin adapter layer adds a small amount of indirection
- `JeeLinkPort` Protocol must be kept in sync with the subset of `pylacrosse` features
  actually used
- Fake adapter must produce realistic enough data to exercise edge cases (e.g.,
  out-of-range values, rapid ID changes)

_2026-03-04_
