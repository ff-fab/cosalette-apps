## Epic Core Domain + Infrastructure: Batch 2 — Registry, Filters, Calibration, Adapters

Implemented the core business logic and hardware abstraction layers: SensorRegistry
with auto-adopt (ADR-002), FilterBank for per-sensor median filtering, calibration
offset application, and both production (PyLaCrosseAdapter) and test
(FakeJeeLinkAdapter) hardware adapters with lazy import (ADR-003).

**Files created/changed:**

- packages/src/jeelink2mqtt/registry.py (new, 311 lines)
- packages/src/jeelink2mqtt/filters.py (new, 59 lines)
- packages/src/jeelink2mqtt/calibration.py (new, 36 lines)
- packages/src/jeelink2mqtt/adapters.py (new, 148 lines)

**Functions created/changed:**

- `SensorRegistry` — bidirectional ID↔name index, auto-adopt, manual assign/reset,
  event logging, JSON serialization
- `FilterBank` — lazy per-sensor-ID MedianFilter pairs (temp + humidity)
- `apply_calibration()` — pure function with `dataclasses.replace()`, half-up rounding,
  humidity clamping
- `PyLaCrosseAdapter` — production adapter with lazy pylacrosse import, frame parsing
- `FakeJeeLinkAdapter` — test adapter with `inject()`/`inject_batch()` helpers

**Tests created/changed:**

- None yet (unit tests are the next task: workspace-4xx.5 and workspace-wog.6)

**Review Status:** APPROVED (all 6 revision items addressed: dead code removed,
replace() used, assign() validates sensor name, thread-safety documented, lifecycle
consistency enforced, humidity rounding clarified)

**Git Commit Message:**

```
feat: add sensor registry, filtering, calibration, and adapters

- SensorRegistry with auto-adopt algorithm (ADR-002) and JSON persistence
- FilterBank for per-sensor median filtering via cosalette.filters
- apply_calibration() with half-up rounding and humidity clamping
- PyLaCrosseAdapter with lazy import and frame parsing (ADR-003)
- FakeJeeLinkAdapter for testing with inject()/inject_batch()
```
