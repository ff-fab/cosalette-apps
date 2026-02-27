# ADR-003: Hardware Abstraction — Hexagonal Architecture

## Status

Accepted **Date:** 2026-02-27

## Context

The vito2mqtt bridge communicates with a Viessmann boiler via a serial Optolink
interface — a physical optical transceiver attached over USB-to-serial. The application
must read boiler parameters (temperatures, pressures, burner hours) and write control
parameters (target temperatures, operating modes) over this serial link.

Hardware abstraction is critical for three reasons: testability (unit and integration
tests must run without physical hardware), development ergonomics (a dry-run mode for
iterating without a connected boiler), and future flexibility (alternative transports
such as TCP-to-serial bridges or simulated devices).

The chosen application framework, cosalette (see ADR-001), provides first-class support
for hexagonal architecture via PEP 544 Protocol-based ports, making this a natural
architectural fit.

## Decision

Use **hexagonal architecture with PEP 544 Protocol ports** to abstract the hardware
layer because it enables full test isolation, dry-run development, and framework-aligned
port/adapter separation with structural subtyping (no inheritance required).

**Key design elements:**

- `OptolinkPort` — the primary Protocol defining `async read(address, length)` and
  `async write(address, data)` operations
- **Connect-per-cycle strategy** — open and close the serial connection each polling
  cycle rather than maintaining a persistent connection
- **Adapter lifecycle via async context manager** — adapters implement `__aenter__` /
  `__aexit__` for resource cleanup
- **Adapters**: `SerialOptolinkAdapter` (real hardware), `FakeOptolinkAdapter` (tests),
  `DryRunOptolinkAdapter` (development without hardware)

## Decision Drivers

- Testability — swap real hardware for a fake adapter in tests without mocking
- Dry-run mode for development without physical boiler hardware
- cosalette's native hexagonal architecture support (Protocol-based port registration)
- PEP 544 structural subtyping — adapters satisfy the port by shape, not inheritance
- Connect-per-cycle simplifies fault tolerance for serial devices (which can hang or
  become unresponsive)

## Considered Options

- **Option 1: Hexagonal with PEP 544 Protocols** — structural typing, Protocol-based
  ports
- **Option 2: ABC-based abstract ports** — nominal typing with abstract base classes
- **Option 3: Direct serial coupling** — no abstraction, serial calls inline

## Decision Matrix

| Criterion                 | PEP 544 Protocols | ABC abstract ports | Direct coupling |
| ------------------------- | ----------------- | ------------------ | --------------- |
| Testability               | 5                 | 4                  | 1               |
| Type safety               | 5                 | 4                  | 2               |
| Framework alignment       | 5                 | 3                  | 1               |
| Implementation complexity | 4                 | 3                  | 5               |
| Runtime overhead          | 5                 | 5                  | 5               |
| **Total**                 | **24**            | **19**             | **14**          |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Full test isolation — unit tests use `FakeOptolinkAdapter` with deterministic
  responses, no serial port required
- Dry-run mode enables development and demo workflows on any machine, including CI
  runners and developer laptops without boiler hardware
- PEP 544 structural subtyping means adapters do not need to inherit from a base class,
  reducing coupling and enabling third-party adapters that satisfy the Protocol by shape
- Connect-per-cycle strategy provides natural fault recovery — if a serial connection
  hangs, the next cycle starts fresh without complex reconnection logic
- Architecture aligns with cosalette's port registration mechanism, reducing integration
  friction

### Negative

- Additional abstraction layer adds indirection that developers must understand when
  tracing a read/write operation from MQTT to serial
- Protocol port interface requires careful upfront design — changes to the port signature
  ripple across all adapters
- Connect-per-cycle adds latency overhead per poll (connection setup/teardown) compared
  to a persistent connection
- `FakeOptolinkAdapter` must be kept in sync with the real adapter's behavior to ensure
  test fidelity

_2026-02-27_
