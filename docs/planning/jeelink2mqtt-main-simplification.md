# Planning: jeelink2mqtt main.py simplification

**Date:** 2026-04-25
**Status:** Awaiting approval
**Benchmark:** `caldates2mqtt/main.py` (~90 lines, fully declarative, no
infrastructure noise)

---

## Diagnosis: why is `receiver` opaque?

`caldates2mqtt` has a single conceptual concern: *poll a calendar, return events*.
The framework handles everything else.

`jeelink2mqtt/main.py` currently has **ten** distinct concerns inside one
`async def receiver` function:

| Concern | Lines | Category |
|---|---|---|
| Adapter lifecycle (`open/register_callback/start_scan`) | ~6 | Infrastructure |
| Thread→async queue bridging | ~8 | Infrastructure |
| Timeout loop with `wait_for` | ~6 | Infrastructure |
| Periodic staleness check | ~4 | Timing |
| Periodic heartbeat re-publish | ~5 | Timing |
| Raw frame publishing | ~2 | Domain |
| Registry routing (`record_reading`) | ~2 | Domain |
| Filter → calibrate → publish pipeline | ~6 | Domain |
| Mapping event draining | ~9 | Domain |
| Persistence (`store["registry"]`) | ~6 | Infrastructure |

The **domain** logic occupies only ~19 of those ~54 lines; the rest is
infrastructure that obscures the intent.

---

## Framework proposals (cosalette changes needed)

### P1 — `@app.state`: lifespan-scoped shared-state factory

**What it does:** A decorator that declares a shared object constructed once
during app bootstrap (after settings resolution, before devices start). The
framework injects it into any handler that declares the matching type parameter —
exactly like the existing adapter injection.

**Implementation sketch:**

```python
@app.state
def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    configs = _build_sensor_configs(settings)
    return SharedState(
        registry=SensorRegistry(configs, settings.staleness_timeout_seconds),
        filter_bank=FilterBank(settings.median_filter_window),
        sensor_configs={c.name: c for c in configs},
    )
```

The framework calls this factory at bootstrap, stores the result, and injects
it anywhere `state: SharedState` appears in a handler signature — no
`lifespan=` argument on `App(...)` needed.

**Why this approach:**

- Follows the existing DI pattern already used for adapters and settings
- Makes the entire app composition visible in `main.py` — the `_lifespan`
  context manager in `app.py` vanishes, and with it the shim module
- Aligns with how IoC containers (Spring, Dagger) handle application-scoped
  beans: declare once, inject everywhere (Single Responsibility + IoC)
- Opens the door to multiple shared-state objects without nesting lifespans

**Trade-offs:**

- Adds a new decorator to the framework surface; needs teardown hook if cleanup
  is required (e.g. `@app.state` returning a context manager)
- `_lifespan` currently supports teardown via `yield`; the new API needs an
  equivalent (`@app.state` accepting an async generator that `yield`s state)

**Impact on main.py:** Eliminates `app.py` shim, removes `lifespan=` from
`App(...)`, and makes `SharedState` construction readable inline.

---

### P2 — `@app.stream`: callback/push adapter archetype

**What it does:** A new archetype for adapters that *push* data via sync
callbacks (common with serial/hardware libraries). The framework:

1. Manages the adapter lifecycle (`open/close/start_scan/stop_scan`) via
   `async with adapter:`
2. Bridges the sync callback to an `AsyncIterator` (internals: `asyncio.Queue`
   + `call_soon_threadsafe`)
3. Exposes a clean `async for reading in stream:` to the handler

The adapter's protocol changes from callback-registration to async-iterator
(or the framework wraps the existing protocol transparently via a secondary
`Streamable` protocol hint).

**Implementation sketch — handler side:**

```python
@app.stream()
async def receiver(
    ctx: cosalette.DeviceContext,
    stream: cosalette.Stream[SensorReading],
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

**Why this approach:**

- Eliminates the single largest block of noise: `asyncio.Queue`, `loop =
  get_running_loop()`, `call_soon_threadsafe`, `asyncio.wait_for`
- Adapter lifecycle becomes the framework's concern — compare how
  `CalDavReader` is injected without lifecycle management in caldates2mqtt
- Generalises to any push-based hardware (serial, GPIO events, WebSocket
  streams) — reusable across apps
- Separation of Concerns: thread-bridging is a cross-cutting infrastructure
  concern; it belongs in the framework, not each app

**Trade-offs:**

- Requires `JeeLinkPort` protocol to gain either `__aiter__` or a marker
  interface so the framework knows to bridge it; existing adapters need
  updating
- The timeout-based loop (needed for periodic tasks) is replaced by
  `@app.periodic` (P3); the two proposals are coupled
- Complex implementation in the framework: thread detection, cancellation,
  backpressure

**Impact on main.py:** Removes ~20 lines of boilerplate; receiver body shrinks
to pure domain logic.

---

### P3 — `@app.periodic`: interval tasks alongside a device

**What it does:** A decorator for background tasks that run on a fixed interval
independently of the main device loop, co-scheduled by the framework.

```python
@app.periodic(interval=timedelta(seconds=1))
async def check_staleness(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    for sensor in settings.sensors:
        if state.registry.is_stale(sensor.name):
            await ctx.publish(f"{sensor.name}/availability", "offline", retain=True)

@app.periodic(interval=setting_ref("heartbeat_interval_seconds"))
async def heartbeat(
    ctx: cosalette.DeviceContext,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    ...  # re-publish last known readings
```

**Why this approach:**

- The current `asyncio.wait_for(..., timeout=1.0)` + `TimeoutError` catch is
  the classic Python pattern for "run something periodically while waiting for
  I/O" — it works, but it is an *implementation hack*, not a declaration of
  intent
- With `@app.periodic`, the staleness and heartbeat concerns become named,
  testable, independently-configured handlers — Single Responsibility
- `setting_ref("heartbeat_interval_seconds")` for the interval is already
  supported in `@app.telemetry` — same syntax works here
- Periodic tasks are a first-class concept in most IoT frameworks (Node-RED,
  HASS automations); cosalette gains expressive parity

**Trade-offs:**

- Requires framework-side task scheduling (co-routine spawning, cancellation
  on shutdown)
- Heartbeat needs access to `last_readings` and `last_publish_time` — mutable
  state currently local to `receiver`. Either these move into `SharedState`, or
  periodic tasks need a shared-memory mechanism
- Adds complexity if a periodic task needs to interact tightly with the device
  loop (e.g. periodic task reads data last written by the device)

**Impact on main.py:** The `TimeoutError` branch in the receiver loop
disappears; `check_staleness` and `heartbeat` become top-level declarations.

---

### P4 — Sub-command dispatch for `@app.command`

**What it does:** Allow `@app.command` to route on a payload field, making
each sub-command a first-class declaration instead of a manual dispatch dict.

```python
@app.command("mapping", sub="assign")
async def cmd_assign(payload: str, state: SharedState) -> dict[str, object]:
    data = json.loads(payload)
    ...

@app.command("mapping", sub="reset")
async def cmd_reset(payload: str, state: SharedState) -> dict[str, object]:
    ...

@app.command("mapping", sub="reset_all")
async def cmd_reset_all(payload: str, state: SharedState) -> dict[str, object]:
    ...

@app.command("mapping", sub="list_unknown")
async def cmd_list_unknown(payload: str, state: SharedState) -> dict[str, object]:
    ...
```

The `sub=` parameter names the field key (default: `"command"`). The framework
dispatches based on `json.loads(payload)["command"]`.

**Why this approach:**

- The current `dispatch = {"assign": ..., "reset": ...}[command](state, data)`
  is a hand-rolled router — idiomatic Python, but opaque in `main.py`
- Four named `@app.command` handlers are individually testable, individually
  documented, and individually visible in the app manifest
- Mirrors how HTTP frameworks (FastAPI, Flask) do method-level routing — one
  function per verb
- Unknown `sub` values can return a framework-standard error automatically

**Trade-offs:**

- Framework needs to understand `sub=` and compose error responses for unknown
  values
- All sub-handlers on the same topic share the MQTT topic path; the framework
  must route before any handler is called
- Alternatively: **`@app.command_group`** decorator that produces a class-based
  command namespace — slightly heavier but more explicit

**Impact on main.py:** The `handle_mapping` function and its dispatch dict
disappear; four short, named functions replace it.

---

## App-level improvements (no framework changes)

### A1 — `JeeLinkPort`: async context manager + async iterator

Redesign the protocol to support `async with jeelink as stream:` +
`async for reading in stream:`. The concrete adapter (`PyLaCrosseAdapter`)
wraps the threading internally. The fake adapter becomes a simple async
generator.

This is a prerequisite for P2 but delivers value independently: if done
without the framework `@app.stream` archetype, the thread bridging moves into
the adapter instead of the receiver, which is still a significant improvement.

**Resulting receiver sketch (app-level only, no framework changes):**

```python
@app.device()
async def receiver(ctx, jeelink: JeeLinkPort, store, settings, state):
    state.restore_from(store, settings)
    async with jeelink as stream:
        async for reading in stream:
            if ctx.shutdown_requested:
                break
            await _publish_raw(ctx, reading)
            name = state.registry.record_reading(reading)
            if name and (config := state.sensor_configs.get(name)):
                calibrated = state.apply_pipeline(reading, config)
                await _publish_sensor(ctx, name, calibrated)
            await state.flush_events(ctx, store)
```

~25 lines instead of ~80. The `TimeoutError` trick for periodic tasks would
require a different approach (e.g. `asyncio.create_task` alongside the loop).

### A2 — Domain methods on `SharedState` / `SensorRegistry`

- `state.restore_from(store, settings)` — move `_receiver._restore_registry`
  onto `SharedState`
- `state.apply_pipeline(reading, config)` — move `_receiver._apply_pipeline`
  onto `SharedState`
- `await state.flush_events(ctx, store)` — encapsulate the 9-line event drain,
  filter reset, mapping state publish, and store persist into one call

These are pure refactorings: the logic moves from `receiver.py` into
`state.py`. The receiver body shrinks and reads as domain intent.

---

## End state: ideal `main.py`

With all proposals implemented:

```python
app = cosalette.App(
    name="jeelink2mqtt",
    version=__version__,
    description="JeeLink LaCrosse sensor bridge for MQTT",
    settings_class=Jeelink2MqttSettings,
    store=lambda s: JsonFileStore(s.data_dir / "jeelink2mqtt.json"),
    adapters={JeeLinkPort: (PyLaCrosseAdapter, FakeJeeLinkAdapter)},
)

@app.state
def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    configs = _build_sensor_configs(settings)
    return SharedState(
        registry=SensorRegistry(configs, settings.staleness_timeout_seconds),
        filter_bank=FilterBank(settings.median_filter_window),
        sensor_configs={c.name: c for c in configs},
    )

@app.stream()
async def receiver(
    ctx: cosalette.DeviceContext,
    stream: cosalette.Stream[SensorReading],
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    state.restore_from(store, settings)
    async for reading in stream:
        await _receiver.publish_raw(ctx, reading)
        name = state.registry.record_reading(reading)
        if name and (config := state.sensor_configs.get(name)):
            calibrated = state.apply_pipeline(reading, config)
            await _receiver.publish_sensor(ctx, name, calibrated)
        await state.flush_events(ctx, store)

@app.periodic(interval=timedelta(seconds=1))
async def staleness_check(ctx, settings, state): ...

@app.periodic(interval=setting_ref("heartbeat_interval_seconds"))
async def heartbeat(ctx, settings, state): ...

@app.command("mapping", sub="assign")
async def cmd_assign(payload: str, state: SharedState) -> dict: ...

@app.command("mapping", sub="reset")
async def cmd_reset(payload: str, state: SharedState) -> dict: ...

@app.command("mapping", sub="reset_all")
async def cmd_reset_all(payload: str, state: SharedState) -> dict: ...

@app.command("mapping", sub="list_unknown")
async def cmd_list_unknown(payload: str, state: SharedState) -> dict: ...

def main() -> None:
    app.run()
```

~80 lines. Every line is a declaration, not mechanism. The `receiver` body
reads as a domain flow: restore → iterate frames → route → pipeline →
flush. Comparable to caldates2mqtt in clarity.

---

## Priority and dependency order

| # | Proposal | Standalone? | Impact | Effort |
|---|---|---|---|---|
| A2 | Domain methods on SharedState | Yes | Medium | Low |
| A1 | JeeLinkPort async iterator | Yes | High | Medium |
| P1 | `@app.state` | Yes | High | Medium |
| P3 | `@app.periodic` | Depends on P2 or A1 | Medium | Medium |
| P4 | Sub-command dispatch | Yes | Medium | Low |
| P2 | `@app.stream` | Depends on A1 | High | High |

**Recommended sequence:**

1. **P1 + A2** (independent, high-value, low-risk) — `@app.state` eliminates
   the shim; domain methods clean up the receiver body without touching the
   adapter or loop structure
2. **A1** (adapter protocol redesign) — prerequisite for P2; independently
   moves thread bridging out of main.py
3. **P3 + P4** (framework additions that work with or without P2)
4. **P2** (framework stream archetype — biggest bang, most complex)
