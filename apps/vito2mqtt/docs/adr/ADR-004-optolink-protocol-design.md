# ADR-004: Optolink Protocol Design

## Status

Accepted **Date:** 2026-02-27

## Context

The Viessmann Optolink interface uses the P300 serial protocol to communicate with the
boiler's control unit. The protocol involves a binary telegram format with checksums, a
session initialization handshake, and typed data encoding for various parameter types
(temperatures as fixed-point integers, operating modes as enumerations, timestamps as
packed BCD, etc.).

A clean, testable protocol implementation is essential because protocol bugs are
difficult to diagnose against real hardware, and the data types have specific byte-level
encoding rules that must be precisely correct. The implementation must support the full
set of Vitodens 200-W parameters while being structured for independent unit testing of
each concern.

This sub-package provides the concrete implementation behind the `OptolinkPort` protocol
defined in ADR-003, connecting the hexagonal architecture's port abstraction to the P300
serial protocol.

## Decision

Implement the P300 protocol as an **internal sub-package** (`vito2mqtt.optolink`) with
**four distinct layers** because separating telegram framing, data type codecs, the
command registry, and session control enables independent testing of each concern and
clear separation of responsibilities.

Use a **clean-room TDD approach**: write behavioral specifications as tests first, then
implement each layer to satisfy the specs. Use **English signal names** throughout the
codebase — these names appear as keys in the MQTT JSON payloads defined in ADR-002.

**Sub-package structure:**

- `telegram.py` — P300 telegram framing: encode outbound telegrams, decode inbound
  responses, compute and validate checksums
- `codec.py` — Data type encoder/decoder supporting IS10, IUNON, IU3600, BA, RT, CT,
  ES, TI, PR2, PR3, and USV type codes
- `commands.py` — Vitodens 200-W command registry mapping addresses to signal names,
  data types, access modes (read/write/read-write), and byte lengths
- `transport.py` — Session controller handling P300 initialization handshake and
  read/write request/response orchestration

## Decision Drivers

- Separation of concerns — each layer handles exactly one responsibility and is
  independently testable
- Clean-room TDD for correctness guarantee — behavioral specs written before
  implementation
- English naming for an international, open-source codebase
- Internal package (not a separate library) — tight coupling to vito2mqtt is acceptable
  since the protocol implementation serves only this application
- Layered design allows swapping or extending individual layers (e.g., adding a new
  codec type) without touching unrelated code

## Considered Options

- **Option 1: Internal sub-package with layered design** — four modules inside
  `vito2mqtt.optolink`
- **Option 2: Separate library** — standalone PyPI package (`optolink-p300`) reusable
  across projects
- **Option 3: Monolithic protocol module** — single `optolink.py` file containing all
  protocol logic

## Decision Matrix

| Criterion             | Layered sub-package | Separate library | Monolithic module |
| --------------------- | ------------------- | ---------------- | ----------------- |
| Testability           | 5                   | 5                | 2                 |
| Maintainability       | 5                   | 4                | 2                 |
| Reusability           | 3                   | 5                | 2                 |
| Development speed     | 4                   | 2                | 4                 |
| Deployment complexity | 5                   | 3                | 5                 |
| **Total**             | **22**              | **19**           | **15**            |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Each layer can be tested in complete isolation — telegram framing tests never touch
  codec logic, codec tests never touch serial I/O
- Clean-room TDD approach produces a comprehensive test suite that serves as living
  documentation of the P300 protocol behavior
- Adding support for a new data type requires only extending `codec.py` and its tests,
  with no changes to telegram framing or transport
- The command registry in `commands.py` provides a single source of truth for all
  supported boiler parameters, making audits and additions straightforward
- English signal names make the codebase accessible to international contributors and
  align with MQTT topic key conventions

### Negative

- Four-layer design adds structural complexity compared to a single-file implementation,
  requiring developers to understand the layer boundaries
- Internal sub-package means the protocol implementation cannot be reused by other
  Viessmann-related projects without extracting it later
- Clean-room TDD demands significant upfront test-writing effort before any
  implementation code exists
- The command registry must be manually maintained as new boiler parameters are
  discovered or firmware updates add capabilities

_2026-02-27_
