# cosalette Framework Enhancement Proposals

**Date:** 2026-04-25
**Author:** jeelink2mqtt maintainer
**Status:** Awaiting framework implementation
**Target app:** `jeelink2mqtt` (reference: `caldates2mqtt` as the simplicity benchmark)

Each proposal is self-contained and independently implementable.  The dependency
order (lowest risk → highest) is: **P1 → P4 → P3 → P2**.

---

## P1 — `@app.state`: lifespan-scoped shared-state factory

### Motivation

Several apps (jeelink2mqtt, gas2mqtt) need a shared object constructed once during
bootstrap, injected by type into every handler that requests it.  Today this requires
an `@asynccontextmanager` function plus `lifespan=` on `App(...)`.  The pattern works
but is verbose and indirect: the construction logic lives outside `main.py` in a
separate module, the `ctx.settings` cast is required, and a shim re-export module is
needed for backward compatibility.

`@app.state` replaces this with a factory the framework calls at bootstrap and stores
in the DI container.

### API

```python
# Sync factory — no teardown needed
@app.state
def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    configs = _build_sensor_configs(settings)
    return SharedState(
        registry=SensorRegistry(configs, settings.staleness_timeout_seconds),
        filter_bank=FilterBank(settings.median_filter_window),
        sensor_configs={c.name: c for c in configs},
    )

# Async generator factory — teardown on shutdown
@app.state
async def shared_state(settings: Jeelink2MqttSettings) -> AsyncIterator[SharedState]:
    state = SharedState(...)
    try:
        yield state
    finally:
        await state.close()   # optional async cleanup
```

Injection: any handler declaring a parameter typed as `SharedState` receives the
same instance.  No import of the factory, no cast, no `ctx.state` workaround.

```python
@app.device()
async def receiver(
    ctx: cosalette.DeviceContext,
    jeelink: JeeLinkPort,
    state: SharedState,          # ← injected automatically
) -> None: ...
```

### Semantics

**Bootstrap order (mandatory):**

1. Settings resolved (`Jeelink2MqttSettings` instantiated from env).
2. All `@app.state` factories called **in registration order**, each receiving the
   resolved `Settings` instance (cast to the declared type).
3. Adapters resolved (`JeeLinkPort` → `PyLaCrosseAdapter` or `FakeJeeLinkAdapter`).
4. Device coroutines started.

**Teardown order (reverse of bootstrap):**

1. Device coroutines cancelled/finished.
2. `@app.state` generators exited in **reverse registration order** (last registered,
   first torn down) — same convention as Python's `contextlib.ExitStack`.
3. Adapters closed.

**Lifecycle variants:**

| Factory form | Teardown |
|---|---|
| `def f(settings) -> T` | No teardown (simple return). |
| `def f(settings) -> ContextManager[T]` | Framework calls `__enter__` / `__exit__`. |
| `async def f(settings) -> AsyncIterator[T]` | Framework enters the async generator; exits on shutdown. |
| `async def f(settings) -> AsyncContextManager[T]` | Framework calls `__aenter__` / `__aexit__`. |

The framework detects the variant by inspecting the return annotation using
`inspect.get_annotations` + `typing.get_origin` / `typing.get_args`.  Unannotated
factories should raise `TypeError` at registration time with a clear message.

**DI key:** The return type annotation (after unwrapping `Iterator[T]`,
`AsyncIterator[T]`, etc.) is used as the DI key.  Two factories returning the same
type should raise `ValueError("Duplicate @app.state for type SharedState")` at
registration time.

**Settings type narrowing:** The factory's first parameter annotation is used to
narrow the settings cast.  If the annotation is a subclass of `cosalette.Settings`,
the framework passes the resolved settings as that type without requiring the app
to cast.  If the parameter is untyped or typed as `cosalette.Settings`, the base
settings instance is passed.

**`lifespan=` compatibility:** `@app.state` and `lifespan=` MUST coexist.  Some apps
(e.g. `suncast`) use `lifespan=` purely for side-effect startup (HTTP server) with
`yield None` — not for DI at all.  The execution order is:

1. `@app.state` factories (in registration order)
2. `lifespan=` context manager entered
3. Devices started

On shutdown, the order reverses.  This gives `lifespan=` the ability to start
services that depend on state objects, if needed.

**Testing:** `AppHarness.override_state(type_, instance)` should be added to allow
tests to inject mock/fake state objects without running the factory.

### What changes in jeelink2mqtt after P1

- `app.py` is **deleted entirely** (the `_lifespan` function it contains moves inline
  as `@app.state` in `main.py`; the re-export shim is no longer needed).
- `lifespan=_lifespan` is removed from `App(...)`.
- Tests that imported `_lifespan` from `app.py` are updated to use
  `AppHarness.override_state(SharedState, fake_state)`.

### What changes in gas2mqtt after P1

- `_gas_lifespan` async context manager function is deleted.
- `lifespan=_gas_lifespan` removed from `App(...)`.
- `cast(Gas2MqttSettings, ctx.settings)` disappears (factory receives typed
  settings directly).

### What does NOT change

- Apps without shared state (`airthings2mqtt`, `caldates2mqtt`, `velux2mqtt`) are
  untouched — `@app.state` is purely additive.
- `suncast` keeps `lifespan=` for its HTTP server side-effect startup.

---

## P2 — `@app.stream`: callback/push adapter archetype

### Motivation

Hardware libraries such as `pylacrosse` deliver data via sync callbacks invoked on a
background serial-reader thread, not via `await`.  Bridging this to asyncio requires:

```python
queue: asyncio.Queue[SensorReading] = asyncio.Queue()
loop = asyncio.get_running_loop()

def _on_reading(reading: SensorReading) -> None:
    loop.call_soon_threadsafe(queue.put_nowait, reading)

jeelink.open()
jeelink.register_callback(_on_reading)
jeelink.start_scan()
try:
    while not ctx.shutdown_requested:
        try:
            reading = await asyncio.wait_for(queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        ...
finally:
    jeelink.stop_scan()
    jeelink.close()
```

This is ~20 lines of framework-level plumbing that every push-adapter app must
duplicate.  `@app.stream` moves it into the framework and exposes an `AsyncIterator`
to the handler.

### Protocol extension: `StreamablePort`

A new protocol, separately importable from `cosalette`:

```python
from typing import Callable, Protocol, runtime_checkable, TypeVar

T_co = TypeVar("T_co", covariant=True)

@runtime_checkable
class StreamablePort(Protocol[T_co]):
    """Adapter protocol for push-based hardware sources.

    Adapters implementing this protocol can be used as the source for
    ``@app.stream`` device handlers.  The framework calls ``open()``,
    ``register_callback()``, and ``start_scan()`` during startup, then
    ``stop_scan()`` and ``close()`` during shutdown.

    The callback is always invoked on the same thread as the caller of
    ``register_callback()`` (or on a background thread — the framework
    handles the asyncio bridge internally).
    """

    def open(self) -> None: ...
    def close(self) -> None: ...
    def start_scan(self) -> None: ...
    def stop_scan(self) -> None: ...
    def register_callback(self, callback: Callable[[T_co], None]) -> None: ...
```

`JeeLinkPort` already satisfies this protocol structurally.  No change to
`JeeLinkPort` is required — `StreamablePort` is checked via `isinstance(...,
StreamablePort)` or by inspecting the `stream:` parameter annotation at
registration time.

### `cosalette.Stream[T]`

A framework-provided type that wraps an `asyncio.Queue[T]` and implements
`AsyncIterator[T]`.  The handler receives an instance; the framework populates it.

```python
class Stream(AsyncIterator[T]):
    """Async iterator over items pushed from a sync callback source.

    Constructed by the framework and injected into ``@app.stream``
    handlers.  Iteration blocks until an item arrives or shutdown is
    requested.

    The stream transparently bridges thread-to-asyncio: items enqueued
    from any thread via the internal callback are safely delivered to
    the ``async for`` loop.
    """

    async def __anext__(self) -> T:
        """Return the next item, or raise StopAsyncIteration on shutdown."""
        ...
```

Internally: `asyncio.Queue[T]`, `asyncio.Event` for shutdown, and a
`call_soon_threadsafe` callback registered with the adapter.

**Shutdown:** When the app begins shutting down, the framework signals the `Stream`
via the internal shutdown event.  Any `await __anext__()` in progress unblocks and
raises `StopAsyncIteration`, exiting the `async for` loop cleanly.  There is no
`timeout=1.0` polling — the stream uses `asyncio.wait` on both the queue and the
shutdown event.

### Decorator syntax

```python
@app.stream(
    summary="JeeLink LaCrosse serial receiver",
)
async def receiver(
    ctx: cosalette.DeviceContext,
    stream: cosalette.Stream[SensorReading],   # ← framework injects
    jeelink: JeeLinkPort,                       # ← adapter, for set_led etc.
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    state.restore_from(store, settings)
    async for reading in stream:
        await _publish_raw(ctx, reading)
        name = state.registry.record_reading(reading)
        if name and (config := state.sensor_configs.get(name)):
            calibrated = state.apply_pipeline(reading, config)
            await _publish_sensor(ctx, name, calibrated)
        await state.flush_events(ctx, store)
```

**Framework responsibilities for `@app.stream`:**

1. Detect the `stream: Stream[T]` parameter by annotation.  Extract `T`.
2. Find the adapter in the DI container that satisfies `StreamablePort[T]`
   (i.e. its `register_callback` callback type matches `Callable[[T], None]`).
   If none found, raise `TypeError` at registration.
3. At startup: `adapter.open()`, `adapter.start_scan()`.
4. Create `Stream[T]` with thread-safe bridge to `asyncio.Queue[T]`.
5. Call `adapter.register_callback(stream._enqueue)`.
6. Inject `Stream[T]` into the handler.
7. At shutdown: signal the stream (unblocks the `async for`), then
   `adapter.stop_scan()`, `adapter.close()` — after the handler has returned.

**Adapter injection alongside stream:** The adapter (`jeelink: JeeLinkPort`) is still
injected normally if declared.  This allows the handler to call adapter methods that
are *not* part of streaming (e.g. `jeelink.set_led()`).  The framework does not
double-open — the adapter lifecycle is managed once.

**What if the handler also wants periodic tasks?** The `async for` loop runs
continuously.  Periodic work (staleness check, heartbeat) should be declared via
`@app.periodic` (P3) and share state via `SharedState` (P1).

### `FakeJeeLinkAdapter` changes required (app-side, not framework)

The fake adapter already implements all five `StreamablePort` methods.  No changes
needed for structural compatibility.  For test ergonomics, the existing `inject()`
and `inject_batch()` helpers continue to work.

### What changes in jeelink2mqtt after P2

- The `asyncio.Queue`, `loop = asyncio.get_running_loop()`, `_on_reading` closure,
  `jeelink.open()`, `jeelink.register_callback()`, `jeelink.start_scan()` lines
  are deleted from `main.py`.
- The `try/finally` with `jeelink.stop_scan()`, `jeelink.close()` is deleted
  (managed by the framework).
- The `asyncio.wait_for(..., timeout=1.0)` + `TimeoutError` branch is deleted
  (periodic work moves to `@app.periodic` via P3).
- The `receiver` body shrinks to ~10 lines of pure domain logic.

### Dependency on P3

P2 removes the `TimeoutError` polling trick.  Without P3, periodic tasks (staleness
check, heartbeat) must be implemented as `asyncio.create_task()` calls inside the
`@app.stream` handler — still much better than the current approach, but not fully
declarative.  P3 completes the picture.

---

## P3 — `@app.periodic`: background interval tasks

### Motivation

The current receiver loop uses `asyncio.wait_for(queue.get(), timeout=1.0)` plus a
`TimeoutError` catch to run two periodic tasks (staleness check, heartbeat).  This
is a well-known Python idiom for "do something every N seconds while waiting for
I/O", but it conflates three concerns in one place: frame processing, staleness
monitoring, and heartbeat.

`@app.periodic` declares interval tasks as first-class named handlers, individually
testable and separately configurable.

### API

```python
@app.periodic(interval=1.0)
async def staleness_check(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    for sensor in settings.sensors:
        if state.registry.is_stale(sensor.name):
            await ctx.publish(f"{sensor.name}/availability", "offline", retain=True)


@app.periodic(interval=cosalette.setting_ref("heartbeat_interval_seconds"))
async def heartbeat(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    now = datetime.now(UTC)
    for sensor in settings.sensors:
        if state.registry.is_stale(sensor.name):
            continue
        last_time = state.last_publish_time.get(sensor.name)
        if last_time and (now - last_time).total_seconds() >= settings.heartbeat_interval_seconds:
            last = state.last_readings.get(sensor.name)
            if last is not None:
                await _publish_sensor(ctx, sensor.name, last)
            await ctx.publish(f"{sensor.name}/availability", "online", retain=True)
            state.last_publish_time[sensor.name] = now
```

### `interval=` parameter

| Form | Meaning |
|---|---|
| `interval=1.0` | Fixed seconds (float). |
| `interval=timedelta(seconds=1)` | Fixed `datetime.timedelta`. |
| `interval=setting_ref("heartbeat_interval_seconds")` | Resolved from settings at bootstrap — same `setting_ref` as `@app.telemetry`. |
| `interval=lambda s: s.heartbeat_interval_seconds` | Callable receiving resolved `Settings`. |

All four forms are already supported by `@app.telemetry`.  `@app.periodic` reuses the
same resolution logic.

### Semantics

**Execution model:**

1. At startup (after `@app.state` factories and adapters, alongside devices), the
   framework spawns one `asyncio.Task` per `@app.periodic` handler.
2. Each task runs a loop:

   ```python
   while not ctx.shutdown_requested:
       try:
           await handler(**injected_kwargs)
       except Exception:
           logger.exception("Periodic task %r raised — continuing", name)
       await asyncio.sleep(interval)
   ```

3. On shutdown, all periodic tasks are cancelled after `ctx.shutdown_requested` is
   set.  The framework waits for them with a configurable grace timeout (default: 5s).

**No MQTT topic binding:** Unlike `@app.telemetry`, periodic handlers are not wired
to any MQTT topic.  They may call `ctx.publish()` directly — this is intentional
(publishing availability is a side-effect with non-standard topic structure).

**DI injection:** Same injection rules as all other handlers — `ctx`, `settings`,
`state` objects, adapters, `logging.Logger`.

**Error handling:** Exceptions are logged and the loop continues.  A periodic task
that raises does not stop the application.  If permanent failure requires stopping,
the handler should call `ctx.request_shutdown()` (or equivalent) explicitly.

**Name:** The function name is used for logging and the app manifest.  Duplicate
names raise `ValueError` at registration time.

**`enabled=callable`:** Supported (same as `@app.telemetry`) — allows a periodic
task to be conditionally enabled based on settings.

**`setting_ref` interaction note:** The heartbeat example above compares against
`settings.heartbeat_interval_seconds` inside the handler body.  With `interval=
setting_ref("heartbeat_interval_seconds")`, the task fires at exactly that interval,
so the body comparison becomes `>= 0` (always true) and can be removed.  This is a
guide for app-side simplification, not a framework requirement.

### What changes in jeelink2mqtt after P3

- `_receiver._check_staleness` call and `_receiver._maybe_heartbeat` call inside
  the `TimeoutError` branch are deleted from `main.py`.
- `last_readings` and `last_publish_time` dicts move from locals in `receiver` to
  fields on `SharedState` (so `@app.periodic` handlers can access them via DI).
- The `asyncio.wait_for` timeout trick becomes unnecessary once P2 removes the
  queue loop; P3 then handles the periodic work cleanly.
- Two new top-level declarations appear in `main.py` (`staleness_check`,
  `heartbeat`), each ~8–10 lines.

### Testing

Periodic tasks should be testable in isolation via direct `await handler(...)` calls.
`AppHarness` should not run periodic tasks by default in unit tests (to keep them
deterministic); a flag `AppHarness.run_periodic=True` should enable them for
integration tests.

---

## P4 — Sub-command dispatch for `@app.command`

### Motivation

The current `handle_mapping` command handler is a 40-line function with a
`dispatch = {command: handler}` dict.  Each sub-command (`assign`, `reset`,
`reset_all`, `list_unknown`) is individually testable only via the dispatch wrapper.
With `sub=`, each becomes a named, independently-testable, individually-documented
first-class declaration.

### API

```python
@app.command("mapping", sub="assign")
async def cmd_assign(
    payload: str,
    state: SharedState,
) -> dict[str, object]:
    data = json.loads(payload)
    ...

@app.command("mapping", sub="reset")
async def cmd_reset(payload: str, state: SharedState) -> dict[str, object]:
    data = json.loads(payload)
    ...

@app.command("mapping", sub="reset_all")
async def cmd_reset_all(payload: str, state: SharedState) -> dict[str, object]:
    ...

@app.command("mapping", sub="list_unknown")
async def cmd_list_unknown(payload: str, state: SharedState) -> dict[str, object]:
    ...
```

All four handlers listen on the **same MQTT topic** (`jeelink2mqtt/mapping/set`).
The framework dispatches based on a field in the JSON payload.

### `sub=` parameter

```
@app.command(topic, sub=value, sub_key="command")
```

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `sub` | `str` | (absent) | The value of `sub_key` in the payload JSON that routes to this handler. If absent, the existing single-handler behaviour is used. |
| `sub_key` | `str` | `"command"` | The JSON field name used for dispatch. Applies per-topic, not per-handler — all handlers on the same topic must use the same `sub_key`. |

**Consistency enforcement at registration:** If multiple `@app.command("mapping",
sub=...)` handlers are registered with different `sub_key` values for the same topic,
the framework raises `ValueError` at registration time.

### Dispatch algorithm (framework, at message receipt)

```python
def _dispatch(topic: str, raw_payload: str) -> dict | None:
    handlers = command_registry[topic]

    if not handlers.has_sub_dispatch:
        # Existing behaviour — single handler
        return await handlers.single(raw_payload)

    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {"error": "Payload is not valid JSON"}

    if not isinstance(data, dict):
        return {"error": "Payload must be a JSON object"}

    sub_key = handlers.sub_key   # e.g. "command"
    sub_value = data.get(sub_key)

    if sub_value is None:
        return {
            "error": f"Missing field '{sub_key}'",
            "known": sorted(handlers.sub_handlers.keys()),
        }

    handler = handlers.sub_handlers.get(sub_value)
    if handler is None:
        return {
            "error": f"Unknown {sub_key}: '{sub_value}'",
            "known": sorted(handlers.sub_handlers.keys()),
        }

    return await handler(raw_payload, **injected_kwargs)
```

**The raw `payload: str` is still passed to the sub-handler unmodified.** Each
sub-handler is responsible for its own `json.loads()`.  This keeps the contract
identical to the existing `@app.command` API and avoids double-parsing.

Alternatively, the framework could parse and inject the data dict directly as
`data: dict[str, object]` if the handler declares that type instead of `str`.  This
is an opt-in convenience; `payload: str` remains the default.

### What changes in jeelink2mqtt after P4

- `handle_mapping` function and its 40-line dispatch dict are **deleted**.
- `commands.py` no longer needs a `_dispatch` helper — each `_handle_*` function
  is called directly as the `@app.command` handler body (or inlined if short enough).
- Four new `@app.command("mapping", sub=...)` declarations appear in `main.py`.
- The `commands.py` module may shrink to 4 thin functions, or be inlined entirely.

### What does NOT change for existing apps

`sub=` is optional.  All existing `@app.command` usages without `sub=` continue to
work unchanged.  Mixing sub-dispatched and non-sub-dispatched handlers on different
topics is allowed.  Mixing them on the **same** topic is a registration error.

### App manifest

`cosalette manifest` should show sub-commands as:

```
mapping/set      [cmd]   sub=assign       → cmd_assign
mapping/set      [cmd]   sub=reset        → cmd_reset
mapping/set      [cmd]   sub=reset_all    → cmd_reset_all
mapping/set      [cmd]   sub=list_unknown → cmd_list_unknown
```

---

## Cross-cutting notes for the implementer

### DI container

All four proposals extend the existing DI container.  The injection order matters:

1. Settings (already resolved before any user code runs)
2. `@app.state` objects (P1) — may depend on settings
3. Adapters — resolved after state (adapters do not depend on `@app.state` objects)
4. Periodic tasks (P3) — launched alongside devices, may depend on 1–3
5. Stream handler (P2) — launched alongside devices, may depend on 1–3
6. Command handlers (P4) — invoked on demand, may depend on 1–3

The DI container lookup for injection should use `isinstance` structural checks, not
exact type identity, to support Protocol-typed parameters.

### `cosalette.testing.AppHarness` additions required

| Proposal | New `AppHarness` API |
|---|---|
| P1 | `override_state(type_, instance)` — bypass factory, inject directly |
| P2 | Automatically uses `FakeAdapter`; `Stream` populated via `harness.inject(reading)` |
| P3 | `run_periodic=False` (default); `await harness.tick_periodic(name)` for unit tests |
| P4 | No change needed — sub-dispatch tested by sending payloads normally |

### Backward compatibility

All four proposals are **additive**.  No existing API is removed or changed.  The
`lifespan=` parameter on `App(...)` remains supported indefinitely (needed by
`suncast` for its HTTP server side-effect).

### Versioning suggestion

- P1 + P4: ship together — low risk, high value, no new protocols
- P3: ship in same or next minor — builds on P1's `SharedState` movement
- P2: ship last — requires `StreamablePort` protocol and `Stream[T]` implementation;
  good candidate for a minor version bump given the new public type
