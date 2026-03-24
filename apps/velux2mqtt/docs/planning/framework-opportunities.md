# Framework Improvement Proposals

These proposals capture framework gaps identified during development of velux2mqtt and
sibling cosalette apps. Each documents a real limitation encountered in production code,
the workaround used, and a proposed framework improvement.

---

## 1. Command Sub-Topic Routing

**Context:** velux2mqtt needs `blind/set` for cover commands AND `blind/calibrate/set`
for calibration. `@app.command` and `@ctx.on_command` only subscribe to
`{prefix}/{name}/set`.

**Current behavior:** One inbound topic per device name — no sub-topic dispatch.

**Workaround:** Multiplex both command types through the single `/set` topic. Payload
inspection distinguishes `{"calibrate": "start"}` from `{"position": 50}`. The `topic`
parameter goes unused (`noqa: ARG001`).

**Proposed improvement:** Allow sub-topic command registration:

```python
@ctx.on_command("calibrate")  # subscribes to {prefix}/{name}/calibrate/set
async def handle_calibrate(payload: str) -> None: ...
```

**Impact:** Clean separation of command namespaces. Enables Home Assistant discovery
per sub-entity without payload multiplexing.

**Apps affected:** velux2mqtt (calibration), vito2mqtt (legionella actions), gas2mqtt
(potential reset/calibration).

---

## 2. Delayed Action / Timed Sequence Primitives

**Context:** Cover movement requires: press GPIO → wait `travel_duration` → press stop.
Every `ctx.sleep()` must be followed by a `ctx.shutdown_requested` guard. velux2mqtt has
~6 shutdown-check points in `_execute_step()` alone.

**Current behavior:** `ctx.sleep()` is shutdown-aware, but no higher-level sequence
abstraction exists.

**Workaround:** Manual `gpio.press()` → `ctx.sleep()` → `ctx.shutdown_requested` chains.
Cleanup (press stop) must be explicitly handled at every exit point.

**Proposed improvement:** A `TimedSequence` builder or `ctx.timed_action()` with
cancellation cleanup:

```python
async with ctx.timed_action() as seq:
    await seq.step(gpio.press, button="up")
    await seq.wait(travel_duration)
    await seq.step(gpio.press, button="stop")
    seq.on_cancel(lambda: gpio.press(button="stop"))
```

**Impact:** Eliminates repetitive shutdown guards. Guarantees cleanup on cancellation.

**Apps affected:** velux2mqtt (cover movement), vito2mqtt (legionella heating cycle
with `asyncio.wait_for` workaround).

---

## 3. Lifespan-Yielded Injectable State

**Context:** jeelink2mqtt's `lifespan` sets up `SharedState` but can't inject it into
device handlers via DI.

**Current behavior:** `AppContext` in lifespan has `.settings` and `.adapter()` but no
way to yield state for injection. `init=` callbacks run after lifespan and can't access
lifespan-created objects.

**Workaround:** Module-level singleton pattern: `_state` global set by lifespan,
accessed via `get_state()`. The docstring explicitly acknowledges this limitation.

**Proposed improvement:** Lifespan yields a value registered in DI (FastAPI pattern):

```python
@asynccontextmanager
async def lifespan(ctx: AppContext) -> AsyncIterator[SharedState]:
    state = SharedState(ctx.settings)
    yield state  # registered in DI, injectable by type

@app.telemetry("sensor", interval=60)
async def sensor(state: SharedState) -> dict[str, object]:
    return state.latest_reading()
```

**Impact:** Eliminates module globals. Enables proper DI for lifespan-created resources.

**Apps affected:** jeelink2mqtt (SharedState singleton), potentially vito2mqtt and
gas2mqtt for shared initialization.

---

## 4. Lazy Device Registration from Settings

**Context:** `app.add_device()` must be called before `app.run()`. Apps that register
devices from settings must eagerly construct settings at module level.

**Current behavior:** No "post-settings, pre-device" registration hook. Devices must be
registered at import time.

**Workaround:** Eagerly construct settings at module level (`_settings = Settings()`)
and loop over config to call `app.add_device()`. This crashes on import for
`--help`/`--version` if required env vars are missing. Settings are constructed twice
(once eagerly, once by the framework).

**Proposed improvement:** A registration hook that runs after settings resolution but
before device startup:

```python
@app.on_configure
def register_devices(settings: Velux2MqttSettings) -> None:
    for cover in settings.covers:
        app.add_device(cover.name, make_handler(cover))
```

**Impact:** Eliminates import-time crashes. Removes double settings construction.
Enables graceful `--help`/`--version`.

**Apps affected:** velux2mqtt (cover loop), gas2mqtt (same eager pattern), jeelink2mqtt
(`create_app()` factory).

---

## 5. Dynamic Sub-Entity Availability

**Context:** velux2mqtt's calibration sub-entity should only be "online" during
calibration. Home Assistant would benefit from per-sub-entity availability.

**Current behavior:** Framework auto-publishes `{device}/availability` at device level.
No sub-entity lifecycle.

**Workaround:** No sub-entity availability published. Calibration state machine
implicitly indicates availability via state topic (`IDLE` = not active).

**Proposed improvement:** Sub-entity context manager with automatic availability:

```python
async with ctx.sub_entity("calibrate") as cal:
    # auto-publishes calibrate/availability = online
    await cal.publish_state({"step": "measuring"})
# auto-publishes calibrate/availability = offline
```

**Impact:** Enables richer Home Assistant discovery. Clean sub-entity lifecycle.

**Apps affected:** velux2mqtt (calibration), vito2mqtt (legionella treatment),
jeelink2mqtt (per-sensor staleness).

---

## 6. Command→Loop Bridge

**Context:** `@app.device` handlers need to receive commands in their main loop. Three
apps have independently developed three different patterns for this.

**Current behavior:** `@ctx.on_command` fires as an asyncio callback. No built-in queue
or message-passing to the device loop.

**Workaround:** Three patterns exist across apps:

1. **velux2mqtt:** inline execution in callback (blocks on long commands)
2. **vito2mqtt:** explicit `asyncio.Queue` bridge (~20 lines boilerplate)
3. **gas2mqtt:** `nonlocal` variable mutation (only works for atomic state changes)

**Proposed improvement:** Built-in command channel pre-wired into `DeviceContext`:

```python
@app.device("blind")
async def blind(ctx: DeviceContext) -> None:
    async for cmd in ctx.commands():
        match cmd.payload:
            case {"position": pos}:
                await move_to(pos)
```

**Impact:** Standardized pattern. Eliminates boilerplate. Prevents blocking-command
bugs.

**Apps affected:** All existing apps — most universally needed gap.
