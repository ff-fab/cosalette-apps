# ADR-007: Telemetry Coalescing Groups

## Status

Accepted **Date:** 2026-03-03

## Context

The vito2mqtt bridge registers 7 telemetry handlers — one per signal domain
(outdoor, hot\_water, burner, heating\_radiator, heating\_floor, system,
diagnosis). Each handler polls its signals from the boiler via the Optolink
serial interface (ADR-003, ADR-004).

In the current cosalette execution model, each telemetry handler runs as an
independent `asyncio.Task` with its own sleep/execute/publish loop. When
multiple handlers share the same polling interval (6 of 7 groups default to
300 s, 1 to 3600 s per ADR-005), each opens a **separate** P300 serial session
at roughly the same wall-clock moment.

This causes several problems on a 4800-baud serial bus:

- **Session overhead** — each P300 handshake costs \~200 ms. Six separate
  sessions at t=300 spend \~1.2 s just on handshakes instead of \~0.2 s.
- **Bus contention** — rapid session cycling stresses the Vitodens controller.
- **Timing drift** — independent sleep loops drift apart because each handler
  sleeps *after* its own (varying-length) execution.
- **Scalability** — adding signal groups linearly increases session count.

The solution must work at the cosalette framework level so that other projects
with shared adapter resources (serial buses, SPI interfaces, rate-limited APIs)
benefit from the same mechanism.

### Key requirements

1. At t=0 (startup), all handlers fire in a single shared session.
2. At coinciding ticks (e.g., t=3600 where both 300 s and 3600 s intervals
   fire), handlers share one session.
3. Arbitrary intervals (300, 400, 550) must coalesce whenever they coincide.
4. The mechanism must be a framework-level feature in cosalette.
5. The user-facing API should be explicit and readable — an `group=` parameter
   on `@app.telemetry()` / `app.add_telemetry()`.

## Decision

Add **coalescing groups** to cosalette's telemetry API — a new optional
`group` parameter on `@app.telemetry()` and `app.add_telemetry()` that declares
which handlers should share execution windows when their intervals coincide.

Handlers in the same coalescing group are managed by a shared **tick-aligned
scheduler** that:

- Uses a priority queue to compute a global timeline of fire events
- Groups all handlers due at the same tick into a sequential batch
- Executes the batch in a single execution window (enabling adapter session
  sharing)
- Preserves per-handler publish strategies, error isolation, persistence, and
  init functions

Handlers without a `group` parameter (or in different groups) run independently,
preserving full backward compatibility.

### User-facing API

```python
# Decorator form
@app.telemetry(name="outdoor", interval=300, group="optolink")
async def poll_outdoor(port: OptolinkPort) -> dict[str, object]:
    ...

# Imperative form
app.add_telemetry(
    name="outdoor",
    func=handler,
    interval=300,
    group="optolink",
)
```

### vito2mqtt usage

```python
def register_telemetry(app: App) -> None:
    for group_name in SIGNAL_GROUPS:
        app.add_telemetry(
            name=group_name,
            func=_make_handler(group_name),
            interval=_get_interval(settings, group_name),
            publish=OnChange(),
            group="optolink",       # ← all share the adapter
        )
```

## Decision Drivers

- Minimize serial bus sessions for slow (4800 baud) Optolink interface
- Deterministic tick-aligned timing eliminates drift
- Explicit `group=` parameter makes coalescing visible and intentional
- Framework-level solution benefits all cosalette projects
- Backward compatible — ungrouped handlers are unaffected
- Per-handler semantics (publish strategy, error isolation, persistence)
  remain intact

## Considered Options

- **Option A: Tick-Aligned Scheduler (implicit, all handlers)** — Replace all
  independent loops with a single global scheduler. All handlers are
  automatically coalesced.
- **Option B: Adapter Keep-Alive** — Keep independent handler tasks, make the
  adapter smart enough to hold sessions open between rapid calls.
- **Option C: Coalescing Groups (explicit `group=` parameter)** — Users
  declare which handlers share execution windows via a `group` parameter.

## Decision Matrix

| Criterion                          | A: Global Scheduler | B: Keep-Alive | C: Coalescing Groups |
| ---------------------------------- | :-----------------: | :-----------: | :------------------: |
| Satisfies all 5 requirements       |          4          |       2       |          5           |
| Framework generalizability         |          5          |       1       |          4           |
| API clarity and readability        |          3          |       5       |          5           |
| Implementation complexity          |          3          |       3       |          3           |
| Deterministic timing (no drift)    |          5          |       2       |          5           |
| Backward compatibility             |          3          |       5       |          5           |
| Handles arbitrary intervals        |          5          |       3       |          5           |
| Session sharing at t=0             |          5          |       2       |          5           |
| **Total**                          |        **33**       |     **23**    |        **37**        |

_Scale: 1 (poor) to 5 (excellent)_

Option C scores highest because it combines deterministic tick-aligned
scheduling with explicit user intent. The `group=` parameter makes the
coalescing behavior readable and intentional — developers can see at a
glance which handlers share resources, which is more valuable for long-term
maintainability than implicit "magic" scheduling.

Option A was close but penalised for implicitly changing the execution model
for all handlers (reduced backward compatibility) and for hiding the
coalescing intent from the reader.

Option B was rejected because it relies on timing heuristics (idle timeouts)
that provide no guarantee of coalescing, especially at startup.

## Consequences

### Positive

- Serial sessions reduced from N (one per handler) to 1 per coinciding tick —
  e.g., 2 sessions per cycle instead of 7 for the default vito2mqtt config
- Deterministic tick alignment eliminates timing drift between grouped handlers
- Explicit `group=` parameter is self-documenting and immediately visible
  in registration code
- Full backward compatibility — existing ungrouped handlers work identically
- Per-handler semantics preserved: each handler retains its own publish
  strategy, error recovery, persistence policy, and init function
- Other cosalette projects can use coalescing groups for SPI buses,
  rate-limited APIs, or any shared-resource scenario

### Negative

- New framework concept for users to learn (mitigated by being opt-in and
  having a clear, single-parameter API)
- Scheduler adds code complexity to cosalette's core execution path
- Within a batch, handlers execute sequentially — for adapters with
  independent resources this is suboptimal (mitigated: this only affects
  handlers that *explicitly* opted into the same group)
- Floating-point tick arithmetic requires care to avoid precision issues
  (mitigated: use integer-millisecond internal representation)

_2026-03-03_
