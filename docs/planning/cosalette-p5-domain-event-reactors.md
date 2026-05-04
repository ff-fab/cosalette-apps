# cosalette Framework Enhancement: P5 — Domain-Event Reactors for `@app.state`

**Date:** 2026-05-04
**Author:** jeelink2mqtt maintainer
**Status:** Proposal — awaiting framework review
**Reference finding:** PR #118 review finding #9 (SRP concern with `SharedState`)

---

## Problem

`@app.state` (P1) solves _construction_ and _DI injection_ of shared state objects,
but leaves the state class responsible for its own I/O side-effects.  The concrete
consequence in jeelink2mqtt:

```python
# SharedState today — mixes domain data WITH I/O
class SharedState:
    registry: SensorRegistry        # domain state
    filter_bank: FilterBank         # domain state
    sensor_configs: dict[...]       # domain state

    async def flush_events(self, ctx, store) -> bool:   # ← I/O concern
        events = self.registry.drain_events()
        for event in events:
            await ctx.publish("mapping/event", ...)     # MQTT publish
        store["registry"] = self.registry.to_dict()    # persistence
        return bool(events)

    async def _publish_mapping_state(self, ctx) -> None:
        await ctx.publish("mapping/state", ...)         # MQTT publish
```

`SharedState` knows about MQTT topics, JSON serialisation, and store keys.  It is
both a _value container_ and an _I/O orchestrator_.  This is a SRP violation.

The root cause is structural: `@app.state` factories only receive `settings`, so the
state object has no framework-provided I/O handle.  When the state needs to publish
or persist, it must accept `ctx` and `store` on every method that has side-effects.

### Why the current workaround falls short

Passing `ctx` and `store` as method parameters:

- Scatters I/O knowledge across the domain class
- Makes every call site in `receiver.py`/`main.py` aware of the I/O dependency chain
- Prevents the state object from being used as a pure value in tests without mocking
  `ctx` and `store`
- Conflicts with the framework's DI philosophy — handlers declare dependencies, the
  framework injects them

---

## Proposed Solution: `@app.react`

A new decorator that registers a **domain-event reactor** — a top-level function in
`main.py` that the framework calls (with full DI injection) whenever a state object
signals pending domain events.

### Core API

```python
@app.react(SharedState, drain="registry.drain_events")
async def on_registry_events(
    events: list[MappingEvent],
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    state: SharedState,
) -> None:
    """I/O side-effects for registry events — published and persisted here, not on state."""
    for event in events:
        await _publish_mapping_event(ctx, event)
        if event.old_sensor_id is not None:
            state.filter_bank.reset(event.old_sensor_id)
    await _publish_mapping_state(ctx, state)
    store["registry"] = state.registry.to_dict()
```

### What changes in `SharedState`

```python
# SharedState after P5 — pure domain state, no I/O
class SharedState:
    registry: SensorRegistry
    filter_bank: FilterBank
    sensor_configs: dict[str, SensorConfig]

    def restore_from(self, store: DeviceStore, settings: ...) -> None: ...
    def apply_pipeline(self, reading: ..., config: ...) -> SensorReading: ...
    def persist_registry_if_due(self, store, now, last_persist_time, ...) -> ...: ...
    # flush_events() → DELETED (replaced by @app.react reactor)
    # _publish_mapping_event() → DELETED (moved to module-level helper)
    # _publish_mapping_state() → DELETED (moved to module-level helper)
```

### What changes in `main.py`

```python
# Before (today):
if await state.flush_events(ctx, store):
    last_persist_time = datetime.now(UTC)

# After P5:
# Nothing — the framework calls on_registry_events automatically
```

The receiver body loses the explicit `flush_events` call.  The framework sees that
`SharedState` has a registered reactor, calls `state.registry.drain_events()`, and
if events are returned, invokes `on_registry_events` with DI injection.

---

## Decorator Specification

### `@app.react(StateType, drain="attr.method")`

| Parameter | Type | Meaning |
|-----------|------|---------|
| `StateType` | `type` | The `@app.state`-registered type this reactor watches. |
| `drain` | `str` | Dotted attribute path on the state object to call for draining events. Must be a zero-argument callable returning a sequence. The framework calls it; if the result is non-empty, the reactor is invoked. |

The function decorated with `@app.react` receives:

- The drained events as its first parameter, typed as `list[T]` where `T` is inferred
  from the return annotation of the drain method.
- Any other DI-injectable parameters declared in the signature (`ctx`, `store`,
  `state`, `settings`, adapters, etc.) — same injection rules as all other handlers.

### Execution model

The framework calls the drain probe **after each device handler iteration** (after
`@app.device` yields / `@app.stream` finishes processing one item).  If events are
present, all registered reactors for that state type are called in registration order
before the next iteration begins.

```
device loop iteration N
  → device handler body executes
  → for each @app.react registered for SharedState:
      events = state.registry.drain_events()
      if events:
          await on_registry_events(events, ctx=..., store=..., state=...)
device loop iteration N+1
```

This is equivalent to `await state.flush_events(ctx, store)` at the end of every
loop, but declared at the composition root level with full DI.

### Registration error conditions

| Condition | Error |
|-----------|-------|
| `StateType` not registered via `@app.state` | `ValueError` at registration time |
| `drain` path does not resolve on `StateType` | `TypeError` at registration time |
| `drain` callable is not zero-argument | `TypeError` at registration time |
| Two reactors registered with the same `drain` path on the same state | Allowed — both called in registration order |

### Testing

Reactors are plain async functions — directly `await`-able in unit tests:

```python
async def test_on_registry_events_publishes() -> None:
    state = _make_shared_state(...)
    state.registry.assign("office", 42)
    events = state.registry.drain_events()
    ctx = FakeDeviceContext()
    store = _make_device_store()

    await on_registry_events(events, ctx=ctx, store=store, state=state)

    assert any(t == "mapping/event" for t, _, _ in ctx.published)
```

`AppHarness` should run registered reactors by default in integration tests (same
lifecycle as device handlers).  A flag `AppHarness.run_reactors=False` disables them
for tests that control the drain loop manually.

---

## Design Rationale

### Why not inject `AppPublisher` into the `@app.state` factory?

An `AppPublisher` handle injected at construction time would still couple the state
class to MQTT.  The goal is a state object that has no knowledge of its I/O
environment — only of its own domain.

### Why not a `Flushable` protocol?

A `Flushable` protocol (`def flush(ctx, store)`) requires the state to accept I/O
parameters, preserving the coupling.  `@app.react` inverts this: the framework polls
the state for events and routes them to standalone functions.

### Why not `asyncio.Queue` / internal event bus?

An in-process event bus adds indirection without benefit here.  The reactor is called
synchronously (in async terms) within the same event loop iteration, so there's no
concurrency benefit.  The framework's DI injection provides all the context the
reactor needs.

### Alignment with existing framework patterns

`@app.react` follows the same compositional style as `@app.state`, `@app.periodic`,
and `@app.command` — all are declarative, top-level registrations in `main.py`, with
the framework owning the lifecycle and DI injection.

---

## What changes after P5 across the codebase

| File | Change |
|------|--------|
| `state.py` | Delete `flush_events`, `_publish_mapping_event`, `_publish_mapping_state` |
| `main.py` | Add `@app.react(SharedState, drain="registry.drain_events")` reactor function; remove `if await state.flush_events(...)` from receiver loop |
| `receiver.py` | No change (already has no direct event publishing) |
| `test_receiver.py` | Move event-publishing tests from `TestSharedStateFlushEvents` to `TestOnRegistryEvents`; `SharedState` tests become purely domain-level |

---

## Dependency on other proposals

P5 is **independent** of P2 (`@app.stream`) and P3 (`@app.periodic`).  It can be
implemented against the current `@app.device` + `@app.state` foundation.

Combining P5 with P2 + P3 gives the cleanest final architecture: the `receiver`
body reduces to ~5 lines of pure domain logic (record reading, apply pipeline,
publish sensor state), with all cross-cutting concerns (events, periodic tasks)
declared at the composition root level.
