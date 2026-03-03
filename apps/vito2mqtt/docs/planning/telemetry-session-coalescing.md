# Telemetry Session Coalescing

## Problem Statement

With the current cosalette architecture, each telemetry handler runs as an
independent `asyncio.Task` with its own sleep/execute/publish loop
(`_run_telemetry` in `_app.py`). When multiple handlers share the same
polling interval (e.g., 6 of 7 groups at 300 s), each one opens a separate
adapter session (Optolink P300 handshake → reads → close) at roughly the
same wall-clock moment but in **separate serial sessions**.

### Why this matters for vito2mqtt

| Concern             | Impact                                            |
| ------------------- | ------------------------------------------------- |
| P300 handshake cost | ~200 ms per session at 4800 baud — cumulative     |
| Bus contention      | Rapid session cycling stresses the heating controller |
| Timing drift        | Handlers drift apart over time (sleep _after_ varying execution) |
| Scalability         | Adding more signal groups linearly increases sessions |

### Requirements

1. **At t=0** (startup), ALL handlers fire in a **single** adapter session,
   regardless of their intervals.
2. **At coinciding ticks** (e.g., t=3600 where `interval=300` and
   `interval=3600` both fire), handlers **share one session**.
3. **Arbitrary intervals** (e.g., 300, 400, 550) must work correctly —
   sessions are shared whenever intervals happen to fire at the same tick.
4. **Framework-level solution** — implemented in cosalette as a generalized
   mechanism so any project benefits.
5. **Preserve "FastAPI for MQTT" API** — the user-facing `@app.telemetry()`
   decorator and `app.add_telemetry()` should feel unchanged or minimally
   changed.

### Current cosalette execution model

```
_start_device_tasks()
  └── for each tel_reg in self._telemetry:
        asyncio.create_task(_run_telemetry(reg, ctx, ...))

_run_telemetry(reg, ctx, ...)      ← one task per handler
  kwargs = resolve_kwargs(...)     ← DI resolved ONCE before loop
  while not ctx.shutdown_requested:
      result = await reg.func(**kwargs)   ← handler called
      publish if should_publish(...)
      await ctx.sleep(reg.interval)       ← independent sleep
```

Key facts:

- One `asyncio.Task` per telemetry handler — no coordination between them.
- DI kwargs (including the adapter/port instance) are resolved once before
  the loop, shared across all iterations.
- `ctx.sleep()` is shutdown-aware but not clock-aligned.
- Adapters are entered via `AsyncExitStack` at app startup and remain alive
  for the entire app lifetime — so **session sharing is technically possible**
  since all handlers share the same adapter instance.
- The adapter instance (`OptolinkPort`) is the same object injected into all
  handlers that request it. The bottleneck is that handlers call
  `read_signals()` on their own schedules, potentially overlapping on the
  serial bus.

---

## Option A: Tick-Aligned Scheduler (Centralized Timeline)

**Core idea:** Replace the independent per-handler sleep loops with a single
centralized scheduler that computes a **timeline of ticks** and groups
handlers by their next fire time.

### How it works

```
┌────────────────────────────────────────────────────────────────┐
│  Scheduler (single asyncio.Task)                               │
│                                                                │
│  t=0:    fire ALL handlers (startup tick)                      │
│  t=300:  fire [outdoor, hot_water, burner, radiator, floor,    │
│           diagnosis]                                           │
│  t=400:  fire [group_with_400s_interval]                       │
│  t=600:  fire [outdoor, hot_water, burner, radiator, floor,    │
│           diagnosis]                                           │
│  t=1200: fire [outdoor, ..., + group_with_400s]  ← coincide!  │
│  t=3600: fire [outdoor, ..., system]              ← coincide!  │
│  ...                                                           │
└────────────────────────────────────────────────────────────────┘
```

At each tick, the scheduler:

1. Computes which handlers fire at this tick
2. Calls them sequentially within a shared execution context
3. Publishes each handler's result to its own device topic
4. Sleeps until the next tick

### Scheduler algorithm

```python
# Priority queue of (next_fire_time, registration)
import heapq

heap = [(0.0, reg) for reg in telemetry_regs]   # all fire at t=0
heapq.heapify(heap)

while not shutdown:
    # Pop all handlers due at the earliest tick
    tick_time = heap[0][0]
    await sleep_until(tick_time)

    batch: list[_TelemetryRegistration] = []
    while heap and heap[0][0] <= tick_time:
        t, reg = heapq.heappop(heap)
        batch.append(reg)
        heapq.heappush(heap, (t + reg.interval, reg))

    # Execute batch — all handlers share this execution window
    for reg in batch:
        result = await reg.func(**reg_kwargs[reg])
        # publish per-device...
```

### Session sharing mechanism

Since all handlers in a batch share the same adapter instance (DI resolves
the same `OptolinkPort` object), and `read_signals()` is sequential (not
concurrent), the serial session naturally stays open across the batch.

**But there's a subtlety:** The `OptolinkAdapter` currently opens/closes
P300 sessions per `read_signals()` call (via the `async with` context manager
pattern inside `read_signal`/`read_signals`). To truly share sessions across
handlers in a batch, we need:

**Sub-option A1: Adapter-side session pooling** — The adapter keeps the P300
session alive between rapid-fire `read_signals()` calls (e.g., with an idle
timeout). No framework change needed beyond the scheduler.

**Sub-option A2: Explicit session scope from framework** — The scheduler opens
a "batch scope" that the adapter can detect. E.g., a `SessionScope` context
manager that the adapter hooks into:

```python
# Framework provides this protocol
class SessionScope(Protocol):
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: object) -> None: ...

# Scheduler calls:
async with adapter_session_scope():
    for reg in batch:
        result = await reg.func(**kwargs)
```

### Advantages

- **Minimizes sessions** — handlers at the same tick share one window
- **Deterministic timing** — tick-aligned, no drift
- **Preserves per-handler publish/strategy logic** — each handler still has
  its own `OnChange`/`Every` strategy
- **Preserves user API** — decorators/add_telemetry unchanged
- **Generalizable** — any cosalette project with adapters sharing a resource
  benefits

### Disadvantages

- **Sequential execution within a tick** — handlers in a batch run serially.
  For Optolink (single serial bus) this is correct and desired. For adapters
  with independent resources (e.g., multiple HTTP APIs), serial execution is
  suboptimal. Could be mitigated with a concurrency policy on the adapter
  registration.
- **Complexity in scheduler** — priority queue, batch extraction, per-handler
  publish/strategy state management. More code in the framework.
- **GCD precision concern** — with floating-point intervals, ticks might miss
  alignment by tiny amounts. Need epsilon-based grouping or integer-ms math.

---

## Option B: Session-Scoped Adapter with Keep-Alive

**Core idea:** Keep the independent per-handler tasks, but make the adapter
smart enough to **keep the serial session alive** when calls arrive in quick
succession.

### How it works

```
Handler 1 (300s): read_signals(outdoor)   ──┐
Handler 2 (300s): read_signals(hot_water)   │ adapter detects rapid-fire calls
Handler 3 (300s): read_signals(burner)      │ keeps P300 session open
  ...                                       │
Handler 7 (3600s): read_signals(system)  ───┘ session closes after idle timeout
```

The adapter maintains:

- A P300 session that's opened on first `read_signals()` call
- An idle timeout (e.g., 2s) that keeps the session alive
- Thread-safe queuing if concurrent calls arrive

### Implementation sketch

```python
class OptolinkAdapter:
    _session: P300Session | None = None
    _session_lock: asyncio.Lock
    _idle_timer: asyncio.Task | None

    async def read_signals(self, names):
        async with self._session_lock:
            if self._session is None:
                self._session = await self._open_session()
            self._reset_idle_timer()
            return await self._session.read_batch(names)

    async def _idle_timeout(self):
        await asyncio.sleep(2.0)
        async with self._session_lock:
            await self._session.close()
            self._session = None
```

### Advantages

- **No framework changes** — fully adapter-level solution
- **Transparent** — handlers don't know about session sharing
- **Works with any timing** — doesn't depend on handlers firing simultaneously
- **Independent handlers preserved** — each has its own error handling,
  strategy, etc.

### Disadvantages

- **No guarantee of coalescing** — if handlers drift (which they will), they
  may not arrive within the idle window, especially after errors or varying
  execution times
- **Doesn't satisfy requirement 1** — at t=0, all handlers fire simultaneously
  as independent tasks. With asyncio, they'll interleave, but there's no
  guarantee they'll hit the adapter within the keep-alive window
- **Adapter complexity** — async locks, idle timers, session lifecycle
- **Not generalizable** — every adapter needing session sharing must implement
  its own keep-alive logic. Other cosalette projects don't benefit
- **Timer-based heuristic** — the 2s timeout is a magic number. Too short →
  sessions close between handlers. Too long → session held open uselessly

---

## Option C: Coalescing Groups (Framework API Extension)

**Core idea:** Add a new framework concept — **coalescing groups** — that
lets users declare which telemetry handlers should share execution windows.

### User API

```python
# New: group= parameter on add_telemetry / @app.telemetry
app.add_telemetry(
    name="outdoor",
    func=handler,
    interval=300,
    group="optolink",     # ← NEW: handlers in the same group coalesce
)

# Or via decorator:
@app.telemetry(name="outdoor", interval=300, group="optolink")
async def poll_outdoor(port: OptolinkPort) -> dict[str, object]:
    ...
```

The framework collects all handlers in the same `group`, and when their
intervals coincide, executes them sequentially within a shared tick.

### How it works

Same as Option A's scheduler, but scoped to groups. Handlers without a
`group` run independently (backward compatible).

### Advantages

- **Explicit opt-in** — only grouped handlers coalesce
- **User control** — the user decides which handlers share resources
- **Backward compatible** — ungrouped handlers work as before
- **Clean API** — a single `group=` parameter

### Disadvantages

- **User must know about coalescing** — violates "FastAPI for MQTT" simplicity.
  The framework should handle this transparently
- **Doesn't handle cross-group coalescing** — if two groups happen to fire at
  the same time, they still run independently
- **Same scheduler complexity as Option A** — but with added group scoping

---

## Decision Matrix

| Criterion                          | A: Tick Scheduler | B: Keep-Alive | C: Coalescing Groups |
| ---------------------------------- | :---------------: | :-----------: | :------------------: |
| Satisfies all 5 requirements       |         5         |       2       |          4           |
| Framework generalizability         |         5         |       1       |          4           |
| Preserves "FastAPI for MQTT" feel  |         5         |       5       |          3           |
| Implementation complexity          |         3         |       3       |          3           |
| Deterministic timing (no drift)    |         5         |       2       |          5           |
| Backward compatibility             |         5         |       5       |          5           |
| Handles arbitrary intervals        |         5         |       3       |          5           |
| Session sharing at t=0             |         5         |       2       |          5           |

_Scale: 1 (poor) to 5 (excellent)_

---

## Recommendation: Option A — Tick-Aligned Scheduler

Option A scores highest because:

1. **All requirements satisfied** — deterministic coalescing at t=0 and at
   all coinciding ticks, with arbitrary intervals
2. **Framework-level, generalized** — any cosalette project with shared
   adapter resources benefits automatically, without user opt-in
3. **No API change** — `@app.telemetry()` and `app.add_telemetry()` stay
   the same. The scheduler is an internal implementation detail
4. **Deterministic** — tick-aligned timing eliminates drift, which is a
   strictly better scheduling model than independent sleep loops

### Open questions for implementation

1. **Floating-point precision** — should intervals be stored as integer
   milliseconds internally? Or use an epsilon for tick grouping?
2. **Per-handler error isolation** — if one handler in a batch raises, the
   others must still execute. The current per-handler try/except in
   `_run_telemetry` needs to be preserved within the batch loop.
3. **Publish strategy state** — each handler's `OnChange`/`Every` strategy
   state is currently managed in `_run_telemetry`. The scheduler must
   maintain per-handler strategy state across ticks.
4. **Init functions** — handlers with `init=` callables need their init
   results available. Run all inits before the scheduler loop starts?
5. **Device store** — persistence per handler must be maintained.
6. **Adapter session scope** — should the framework provide a protocol for
   adapters to opt into session batching? Or rely on the serial execution
   within a tick being fast enough that the adapter's natural connection
   stays alive?
7. **Non-telemetry devices** — `@app.device()` handlers are long-running
   coroutines, not polled. They remain independent tasks (unaffected).
8. **Testing** — `AppHarness` needs to work with the new scheduler.
   `FakeClock` must interact correctly with tick-based sleeping.

### Suggested implementation phases

1. **Phase 1: Scheduler core** — Replace `_start_device_tasks` +
   `_run_telemetry` with a `_TelemetryScheduler` that uses a priority
   queue and tick-based dispatch. Maintain all existing per-handler
   semantics (strategy, persistence, error isolation, init).

2. **Phase 2: Adapter session scope (optional)** — If needed, add a
   `SessionScope` protocol that adapters can implement. The scheduler
   opens the scope before a batch and closes it after. For adapters
   that don't implement it, behavior is unchanged.

3. **Phase 3: vito2mqtt integration** — Update `register_telemetry()` if
   any API changes are needed (likely none — just a framework upgrade).

---

## Next Steps

1. [ ] Review and approve this plan
2. [ ] Create ADR for the scheduler change in cosalette
3. [ ] Implement in cosalette (Phase 1 + optional Phase 2)
4. [ ] Update vito2mqtt to use the new cosalette version
