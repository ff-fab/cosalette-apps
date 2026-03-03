# Coalescing Groups: cosalette Framework Requirements

**ADR:** [ADR-007](../adr/ADR-007-telemetry-coalescing-groups.md)
**Analysis:** [telemetry-session-coalescing.md](telemetry-session-coalescing.md)
**Target:** cosalette v0.2.0

---

## 1. Objective

Implement **coalescing groups** in cosalette so that telemetry handlers sharing
a `group` name execute together at coinciding tick boundaries, sharing one
adapter session window. Per ADR-007, the user declares grouping via an explicit
`group=` parameter on the registration API.

---

## 2. User-Facing API Changes

### 2.1 `@app.telemetry()` Decorator

```python
# Current signature (cosalette 0.1.5)
def telemetry(
    self,
    name: str | None = None,
    *,
    interval: float,
    publish: PublishStrategy | None = None,
    persist: PersistPolicy | None = None,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
) -> Callable[..., Any]: ...

# New signature — add group parameter
def telemetry(
    self,
    name: str | None = None,
    *,
    interval: float,
    publish: PublishStrategy | None = None,
    persist: PersistPolicy | None = None,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
    group: str | None = None,       # ← NEW
) -> Callable[..., Any]: ...
```

### 2.2 `app.add_telemetry()` Imperative Method

```python
# Current signature
def add_telemetry(
    self,
    name: str,
    func: Callable[..., Awaitable[dict[str, object] | None]],
    *,
    interval: float,
    publish: PublishStrategy | None = None,
    persist: PersistPolicy | None = None,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
) -> None: ...

# New signature
def add_telemetry(
    self,
    name: str,
    func: Callable[..., Awaitable[dict[str, object] | None]],
    *,
    interval: float,
    publish: PublishStrategy | None = None,
    persist: PersistPolicy | None = None,
    init: Callable[..., Any] | None = None,
    enabled: bool = True,
    group: str | None = None,       # ← NEW
) -> None: ...
```

### 2.3 Semantic Contract

| `group` value  | Behavior                                                 |
| -------------- | -------------------------------------------------------- |
| `None`         | Independent task — identical to cosalette 0.1.5 behavior |
| `"optolink"`   | Joins coalescing group `"optolink"`                      |

- Multiple groups are supported (e.g., `"optolink"`, `"spi_bus"`)
- Handlers in the same group coalesce when their intervals coincide
- Handlers in different groups never interact
- `None`-group handlers always run independently

### 2.4 Validation Rules

| Condition                    | Result                                          |
| ---------------------------- | ----------------------------------------------- |
| Empty string `group=""`     | Raise `ValueError("group must be non-empty")`   |
| Duplicate name within group | Existing name-uniqueness check already catches   |
| Non-positive interval        | Existing validation already catches               |

---

## 3. Internal Data Model Changes

### 3.1 `_TelemetryRegistration` (frozen dataclass)

**File:** `_registration.py:44`

Add one field:

```python
@dataclass(frozen=True, slots=True)
class _TelemetryRegistration:
    name: str
    func: Callable[..., Awaitable[dict[str, object] | None]]
    injection_plan: list[tuple[str, type]]
    interval: float
    is_root: bool = False
    publish_strategy: PublishStrategy | None = None
    persist_policy: PersistPolicy | None = None
    init: Callable[..., Any] | None = None
    init_injection_plan: list[tuple[str, type]] | None = None
    group: str | None = None        # ← NEW — must be LAST (or use kw_only)
```

> **Consideration:** Since `frozen=True` + `slots=True`, the field must be in
> the dataclass definition. All `_TelemetryRegistration(...)` call sites must
> be updated.

---

## 4. Scheduler Design

### 4.1 Architecture Overview

```
_start_device_tasks()
  ├── Partition self._telemetry by reg.group
  │
  ├── For group=None registrations:
  │     asyncio.create_task(_run_telemetry(reg, ctx, ...))   ← unchanged
  │
  └── For each non-None group:
        asyncio.create_task(
            _run_telemetry_group(group_name, group_regs, contexts, ...)
        )
```

### 4.2 Tick-Aligned Scheduler Algorithm

The scheduler uses a **priority queue** (min-heap) of tick events. Each entry
is a `(fire_time, handler_index)` pair. Handlers in the same group that share
a fire time execute sequentially in a single batch.

```
ALGORITHM: _run_telemetry_group(group_name, registrations, contexts, ...)

  1. INIT: For each registration reg[i]:
       a. Prepare providers, device_store, kwargs (same as _run_telemetry)
       b. Run init function if present
       c. Bind publish strategy to clock
       d. Set next_fire[i] = 0.0  (all fire at t=0)
       e. Push (0.0, i) into priority queue

  2. epoch = clock.now()

  3. LOOP while not shutdown:
       a. Pop all entries from queue where fire_time == min fire_time
          → batch = [(fire_time, i), ...]  (all handlers due at this tick)
       b. Compute wait_seconds = (epoch + fire_time) - clock.now()
          If wait_seconds > 0: await ctx.sleep(wait_seconds)
       c. For each handler i in batch (sequential execution):
            - Call reg[i].func(**kwargs[i])
            - Handle None result (persist + continue to next handler)
            - Evaluate _should_publish_telemetry(result, last_published[i], strategy[i])
            - Publish if needed, call strategy.on_published()
            - Persist if needed
            - Clear/handle errors per handler
       d. For each handler i in batch:
            next_fire[i] += reg[i].interval
            Push (next_fire[i], i) into priority queue

  4. CLEANUP: Save device stores on shutdown
```

### 4.3 Key Design Decisions

#### Tick Time Representation

Use **integer milliseconds** internally to avoid floating-point accumulation
errors:

```python
_PRECISION = 1000  # milliseconds

def _to_ms(seconds: float) -> int:
    return round(seconds * _PRECISION)

# Internal tick arithmetic uses int; sleep uses float
interval_ms = _to_ms(reg.interval)
next_fire_ms[i] += interval_ms
wait_seconds = (next_fire_ms_min / _PRECISION) - elapsed
```

This ensures intervals like 300.0 s and 3600.0 s always coalesce exactly at
t=3600 (300×12 == 3600×1), which would not hold under naive `float` addition.

#### Error Isolation

Per-handler errors are **isolated** within a batch:

- If handler `i` raises, catch the exception, call `_handle_telemetry_error()`
  for that handler, then **continue** to handler `i+1`.
- The failing handler is still rescheduled at its next tick.
- Only `asyncio.CancelledError` propagates (shutdown).

#### Execution Order Within Batch

Handlers in a batch execute in **registration order** (the order `add_telemetry`
was called). This is deterministic and documented.

#### Shutdown Behavior

- The scheduler checks `ctx.shutdown_requested` at the top of each loop
  iteration and before each sleep.
- On shutdown, all device stores for grouped handlers are saved (same as
  the `finally` block in `_run_telemetry`).
- The scheduler task is cancelled the same way as independent telemetry
  tasks — via `_cancel_tasks()` in `_run_lifespan_and_devices`.

#### Init Function Handling

Init functions run **once per handler** during the scheduler's initialization
phase (step 1), before the first tick. If an init function fails, that handler
is **excluded** from the group (logged + health reported) but the scheduler
continues for remaining handlers.

---

## 5. Adapter Session Scope

### Current Behavior

Adapters are resolved once at startup. Every `DeviceContext` holds a reference
to the **same** adapter instance via the shared `adapters: dict[type, object]`
dict. The adapter's `__aenter__`/`__aexit__` are called once by the
`AsyncExitStack` in `_resolve_adapters()`.

For `OptolinkAdapter`, each handler call to `read_signals()` currently creates
its own P300 session internally (connect → handshake → reads → close). The
adapter is shared, but sessions are independent.

### Coalescing Impact

Within a coalesced batch, handlers execute **sequentially** and all resolve the
**same** adapter instance (already works — no framework change needed). Session
coalescing at the **adapter level** (keeping one P300 session open across
multiple handler calls in a batch) is a separate concern that belongs in the
adapter implementation, not the framework.

**Decision:** The framework guarantees sequential execution within a batch.
Adapter-level session optimization is a vito2mqtt concern, addressed separately
in `OptolinkAdapter.read_signals()` or a batch-aware wrapper.

---

## 6. Context Management

### DeviceContext per Handler

Each handler in a group still gets its **own** `DeviceContext`. This is required
because:

- `publish_state()` publishes to a handler-specific MQTT topic
  (`{prefix}/{handler_name}/state`)
- Logging is per-handler (`cosalette.{handler_name}`)
- The `DeviceStore` is per-handler

The scheduler receives a `dict[str, DeviceContext]` mapping handler names to
their contexts (same map already built by `_build_contexts()`).

### Sleep Delegation

The scheduler calls sleep on a **single** representative context (e.g., the
first handler's context, or a dedicated group context). The sleep is
shutdown-aware and will return early if `shutdown_event` is set.

---

## 7. Dependency Injection

No changes to the DI system. Each handler's `kwargs` are resolved once during
init (same as current `_run_telemetry`). The resolved kwargs include the
adapter instance, which is already shared.

```python
# Per-handler init (unchanged)
providers[i] = build_providers(ctx[i], reg[i].name)
kwargs[i] = resolve_kwargs(reg[i].injection_plan, providers[i])
```

---

## 8. Publish Strategy State

Each handler retains its **own** `PublishStrategy` instance. The scheduler
calls the strategy methods on a per-handler basis:

```python
strategy = strategies[i]
if self._should_publish_telemetry(result, last_published[i], strategy):
    await ctx.publish_state(result)
    last_published[i] = result
    if strategy is not None:
        strategy.on_published()
```

Strategies that carry state (`Every(seconds=N)` with `_last_publish_time`,
`Every(n=N)` with `_counter`) work correctly because each handler has its own
instance.

---

## 9. Impacted Source Files

| File               | Lines    | Change Description                            |
| ------------------ | -------- | --------------------------------------------- |
| `_registration.py` | ~44-56   | Add `group: str \| None = None` field          |
| `_app.py`          | ~458-572 | Add `group` param to `telemetry()` decorator   |
| `_app.py`          | ~573-656 | Add `group` param to `add_telemetry()`         |
| `_app.py`          | ~1556    | Update `_start_device_tasks()` to partition by group and spawn scheduler tasks |
| `_app.py`          | NEW      | Add `_run_telemetry_group()` scheduler method  |
| `_app.py`          | ~896-975 | `_run_telemetry()` unchanged — still handles ungrouped |

### Files NOT Changed

| File               | Reason                                              |
| ------------------ | --------------------------------------------------- |
| `_context.py`      | `DeviceContext` unchanged; per-handler contexts work |
| `_injection.py`    | DI unchanged; kwargs still resolved per-handler     |
| `_strategies.py`   | Strategies unchanged; per-handler instances          |
| `_clock.py`        | `ClockPort` unchanged; scheduler reads `.now()`     |
| `testing/_clock.py`| `FakeClock` unchanged; tests set `._time` directly  |
| `testing/_harness.py`| `AppHarness` unchanged; already injects test doubles |

---

## 10. Testing Requirements

### 10.1 Unit Tests for Scheduler Logic

| Test Case                                  | Assertion                                          |
| ------------------------------------------ | -------------------------------------------------- |
| Single handler in group                    | Behaves identically to ungrouped handler            |
| Two handlers, same interval                | Both fire on every tick                             |
| Two handlers, different intervals (300, 600)| Both fire at t=0, only 300 at t=300, both at t=600 |
| Three handlers (300, 400, 600)             | Correct batching at all ticks through t=1200        |
| All handlers fire at t=0                   | All execute in first batch, single sleep between    |
| Handler returns `None` in batch            | Next handler still executes                         |
| Handler raises in batch                    | Error isolated, next handler still executes         |
| Init failure excludes handler              | Scheduler runs remaining handlers                   |
| `OnChange` strategy per handler            | Each handler's state tracked independently          |
| `Every(seconds=N)` per handler             | Each handler's counter/timer independent            |
| Shutdown during sleep                      | Scheduler exits cleanly, stores saved               |
| Shutdown between handlers in batch         | Remaining handlers skipped, stores saved            |
| Float precision (300 × 12 == 3600)         | Intervals coalesce at expected ticks                |
| Registration order preserved               | Handlers execute in registration order within batch |

### 10.2 Integration Tests

| Test Case                                  | Assertion                                          |
| ------------------------------------------ | -------------------------------------------------- |
| Grouped + ungrouped handlers coexist       | Each executes independently                         |
| Multiple groups                            | Scheduler tasks are independent                     |
| Full `AppHarness` with grouped telemetry   | MQTT messages published at correct intervals        |
| `FakeClock` time advance                   | Scheduler fires ticks at expected times             |

### 10.3 Backward Compatibility Tests

| Test Case                                  | Assertion                                          |
| ------------------------------------------ | -------------------------------------------------- |
| `group=None` (default)                     | Independent task, identical to v0.1.5               |
| Existing tests pass without modification   | No behavioral regression                            |

---

## 11. Implementation Phases

### Phase 1: Data Model + API Surface

**Scope:** Registration-layer changes only. No scheduler yet.

1. Add `group: str \| None = None` to `_TelemetryRegistration`
2. Add `group` parameter to `telemetry()` decorator — thread to registration
3. Add `group` parameter to `add_telemetry()` — thread to registration
4. Add validation: reject empty string `group=""`
5. Tests: verify `group` field stored, validation, backward compat

**Acceptance:** All existing tests pass. New tests verify `group` field.

### Phase 2: Scheduler Core

**Scope:** The `_run_telemetry_group()` method + partitioning in
`_start_device_tasks()`.

1. Create `_run_telemetry_group()` with tick-aligned priority-queue algorithm
2. Update `_start_device_tasks()` to partition registrations by group
3. Integer-millisecond tick arithmetic with `_to_ms()` helper
4. Per-handler error isolation within batch
5. Init function handling with exclusion on failure
6. Tests: single-handler group, multi-handler same interval, mixed intervals,
   error isolation, init failure, shutdown

**Acceptance:** Grouped handlers coalesce correctly. Ungrouped handlers
unchanged.

### Phase 3: Edge Cases + Polish

**Scope:** Floating-point precision, shutdown semantics, integration tests.

1. Float precision tests (300 × 12 == 3600)
2. Shutdown between handlers in batch
3. Integration tests with `AppHarness` and `FakeClock`
4. Multiple groups running simultaneously
5. Documentation: update cosalette README/docs

**Acceptance:** Full test coverage. All edge cases handled. Docs updated.

### Phase 4: vito2mqtt Integration

**Scope:** Update vito2mqtt to use `group="optolink"`.

1. Update `register_telemetry()` in `devices/telemetry.py` — add `group="optolink"`
2. Bump cosalette dependency to 0.2.0
3. Update tests
4. Verify session coalescing in integration test

**Acceptance:** All 7 handlers in same group. Session count drops from 7 → 1
at coinciding ticks.

---

## 12. Open Questions

### Q1: Priority Queue Implementation

**Options:**
- A) `heapq` from stdlib (simple, proven)
- B) Custom sorted deque (simpler for small N)

**Recommendation:** `heapq` — it handles arbitrary N, is well-tested, and the
semantic match (always pop minimum fire time) is exact.

### Q2: Scheduler Context for Sleep

**Options:**
- A) Use first handler's `DeviceContext` for sleep calls
- B) Create a dedicated "group context" (synthetic, no MQTT topic)

**Recommendation:** Option A for simplicity. The sleep call just needs
shutdown awareness, which any handler's context provides.

### Q3: Adapter Session Optimization (out of scope)

Whether `OptolinkAdapter` should keep a P300 session open across sequential
batch calls is a **vito2mqtt adapter concern**, not a framework requirement.
The framework guarantees sequential execution; the adapter decides whether to
reuse the session. This can be addressed in a separate ADR/task.

---

## Appendix A: Current `_run_telemetry()` Source

```python
async def _run_telemetry(
    self,
    reg: _TelemetryRegistration,
    ctx: DeviceContext,
    error_publisher: ErrorPublisher,
    health_reporter: HealthReporter,
) -> None:
    providers, device_store = self._prepare_telemetry_providers(reg, ctx)

    if reg.init is not None:
        try:
            init_result = _call_init(reg.init, reg.init_injection_plan, providers)
            providers[type(init_result)] = init_result
        except Exception as exc:
            await self._handle_telemetry_error(
                reg, exc, None, error_publisher, health_reporter
            )
            return

    kwargs = resolve_kwargs(reg.injection_plan, providers)
    strategy = reg.publish_strategy
    if strategy is not None:
        strategy._bind(ctx.clock)
    last_published: dict[str, object] | None = None
    last_error_type: type[Exception] | None = None

    try:
        while not ctx.shutdown_requested:
            try:
                result = await reg.func(**kwargs)
                if result is None:
                    self._maybe_persist(
                        device_store, reg.persist_policy, False, reg.name
                    )
                    await ctx.sleep(reg.interval)
                    continue
                if self._should_publish_telemetry(result, last_published, strategy):
                    await ctx.publish_state(result)
                    last_published = result
                    did_publish = True
                    if strategy is not None:
                        strategy.on_published()
                else:
                    did_publish = False
                self._maybe_persist(
                    device_store, reg.persist_policy, did_publish, reg.name
                )
                last_error_type = self._clear_telemetry_error(
                    reg.name, last_error_type, health_reporter,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error_type = await self._handle_telemetry_error(
                    reg, exc, last_error_type, error_publisher, health_reporter,
                )
            await ctx.sleep(reg.interval)
    finally:
        self._save_store_on_shutdown(device_store, reg.name)
```

## Appendix B: Current `_start_device_tasks()` Source

```python
def _start_device_tasks(
    self,
    contexts: dict[str, DeviceContext],
    error_publisher: ErrorPublisher,
    health_reporter: HealthReporter,
) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = []
    for dev_reg in self._devices:
        tasks.append(
            asyncio.create_task(
                self._run_device(
                    dev_reg, contexts[dev_reg.name], error_publisher
                ),
            ),
        )
    for tel_reg in self._telemetry:
        tasks.append(
            asyncio.create_task(
                self._run_telemetry(
                    tel_reg, contexts[tel_reg.name],
                    error_publisher, health_reporter,
                ),
            ),
        )
    return tasks
```
