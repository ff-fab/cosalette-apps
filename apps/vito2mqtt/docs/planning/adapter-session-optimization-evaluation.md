# Evaluation: Adapter Session Optimization

**Gate task:** `workspace-6xf`
**Status:** Closed — won't do
**Evaluated:** 2026-03-06
**Revisit when:** Serial bus reliability issues, polling intervals < 5 s, or cosalette
adds a framework-level session protocol

## Question

Should `OptolinkAdapter` keep the P300 serial session open across sequential batch calls
within a coalescing group tick, instead of opening/closing per handler invocation?

## Current Architecture

The system has three layers of session management:

1. **Framework (cosalette)** — Coalescing group scheduler batches handlers with matching
   fire times and executes them sequentially within `_process_group_handler_result()`.
   This guarantees no concurrent adapter access within a batch.

2. **Adapter (`OptolinkAdapter`)** — Uses connect-per-call strategy. Each
   `read_signals()` call acquires `self._lock`, opens the serial port, performs the P300
   handshake, reads N signals, and closes.

3. **Handler (`_make_handler`)** — Each telemetry handler calls
   `port.read_signals(group_signals)` once per tick, batch-reading all signals in its
   group via a single session.

## Key Finding

Session reuse **already happens within each handler**. Each handler batch-reads via
`read_signals()`, which opens one session for its entire signal group (e.g., all 3
outdoor signals in one session, all 4 burner signals in one session). The question is
whether we should also keep the session open **between** handlers within a coalescing
tick.

## Cost Analysis

**Current cost per coalescing tick (7 groups, all at same interval):**

- 7 serial opens + 7 P300 handshakes + 7 serial closes
- ~25 total signal reads spread across 7 sessions

**With cross-handler session reuse:**

- 1 serial open + 1 P300 handshake + 1 serial close
- Same ~25 signal reads in 1 session

**Estimated savings:** ~50–100 ms per tick (6 fewer open/close/handshake cycles at 4800
baud).

## Complications

1. **Interface change needed** — `OptolinkPort` would need a session management protocol
   (enter/exit). This is a port-level API change affecting all adapters (real, fake,
   dry-run).

2. **Framework coupling** — The framework doesn't know about adapter sessions. Adding
   session awareness would require either a new framework protocol (`SessionPort`) or
   pushing session management into `__aenter__`/`__aexit__` (already used for lifecycle,
   not per-tick).

3. **Error isolation risk** — Currently if one handler's session fails, only that handler
   gets an error. With a shared session, a mid-batch serial error could cascade to
   remaining handlers in the tick.

4. **Lock already serializes** — The `asyncio.Lock` in `OptolinkAdapter` ensures
   sequential access. Within a coalescing batch, the framework already guarantees
   sequential execution, so the lock is uncontended. The overhead is just the serial
   open/close, not lock contention.

5. **Polling intervals are 60–300 seconds** — Saving 50–100 ms per tick that fires every
   60+ seconds is a ~0.1% improvement.

## Decision

**No action needed.** The biggest win — N signals batched into 1 session per group — is
already captured by `read_signals()`. Cross-handler session reuse offers negligible
savings (~0.1%) at significant API complexity cost.

## References

- [ADR-003](../adr/ADR-003-hardware-abstraction.md) — Hardware Abstraction
- [ADR-004](../adr/ADR-004-optolink-protocol-design.md) — Optolink Protocol Design
- [ADR-007](../adr/ADR-007-telemetry-coalescing-groups.md) — Telemetry Coalescing Groups
- `packages/src/vito2mqtt/adapters/serial.py` — OptolinkAdapter implementation
- `docs/planning/coalescing-groups-framework-requirements.md` §5, Q3
