# Adopter Migration Guide — cosalette v0.2.x

**Purpose:** Comprehensive migration guide for the cosalette-apps monorepo maintainer.
Maps every v0.3.0 framework feature (Epics 1–8) to each app, with step-by-step migration
instructions and before/after examples.

**Target version:** cosalette 0.3.x

**Date:** 2026-04-16

---

## Feature × App Matrix

| Feature               | airthings | caldates | gas | jeelink | velux | vito |
| --------------------- | --------- | -------- | --- | ------- | ----- | ---- |
| 1. on_configure       | ○         | ●        | ●   | -       | ●     | -    |
| 2a. ctx.commands()    | ○         | ●        | ●   | -       | ●     | ●    |
| 2b. Sub-topic routing | -         | -        | ○   | -       | ●     | ●    |
| 3. Retry/backoff      | ●         | ●        | ●   | -       | -     | ●    |
| 4. Lifespan yield     | -         | -        | ○   | ●       | -     | ○    |
| 5. Health check       | ●         | -        | -   | ●       | ●     | ●    |
| 6. Auto-restart       | ●         | -        | -   | ●       | ●     | ●    |
| 7. sleep_until        | -         | ●        | -   | -       | -     | -    |
| 8. Sub-entity         | -         | -        | -   | ○       | ●     | ●    |

**Legend:** ● = direct beneficiary, ○ = potential/future, - = not applicable

---

## Per-Feature Migration

### 1. on_configure (ADR-023) — cosalette ≥ 0.3.0

#### What it replaces

Module-level settings access that crashes `--help` (settings instantiated at import time
before the CLI parser runs).

#### Which apps benefit

- **●** caldates, gas, velux (direct — currently use module-level patterns)
- **○** airthings (potential future use)

#### Migration steps

1. Remove module-level `Settings()` instantiation.
2. Move device registration into an `@app.on_configure`-decorated function.
3. Declare dependencies as function parameters — the framework injects them via DI.

**Before (caldates2mqtt):**

```python
_settings = CalDates2MqttSettings()  # crashes --help
for _cal in _settings.calendars:
    app.add_device(_cal.key, make_calendar_handler(_cal))
```

**After:**

```python
@app.on_configure
def register_devices(settings: CalDates2MqttSettings) -> None:
    for cal in settings.calendars:
        app.add_device(cal.key, make_calendar_handler(cal))
```

#### Breaking changes

None — additive. Existing module-level code continues to work but should be migrated to
avoid the `--help` crash.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- `on_configure` runs **after** adapter construction but **before** device startup.
- Both sync and async handlers supported.
- DI-injectable types: `Settings`, adapters, `Logger`, `ClockPort`.

---

### 2a. Command Channel — ctx.commands() (ADR-025) — cosalette ≥ 0.3.0

#### What it replaces

Manual `asyncio.Queue` + hand-rolled `wait_for` timeout loops for consuming commands.

#### Which apps benefit

- **●** caldates, gas, velux, vito (direct — currently use manual queue patterns)
- **○** airthings (potential future use)

#### Migration steps

1. Remove the `asyncio.Queue` and the `@ctx.on_command` callback that feeds it.
2. Replace the `while`/`wait_for` loop with `async for cmd in ctx.commands()`.
3. Access `cmd.payload`, `cmd.topic`, `cmd.sub_topic`, `cmd.timestamp` on the `Command`
   frozen dataclass.

**Before (vito2mqtt):**

```python
command_queue: asyncio.Queue[str] = asyncio.Queue()
@ctx.on_command
async def _handle_command(topic: str, payload: str) -> None:
    await command_queue.put(json.loads(payload).get("action"))
while not ctx.shutdown_requested:
    try:
        action = await asyncio.wait_for(command_queue.get(), timeout=5)
    except TimeoutError:
        continue
```

**After:**

```python
async for cmd in ctx.commands():
    action = json.loads(cmd.payload).get("action")
    await handle(action)
```

#### Breaking changes

None — additive. The old `@ctx.on_command` (no sub-topic) still works.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- `ctx.commands(timeout=None)` blocks indefinitely by default — the framework handles
  graceful shutdown.
- `Command` is a frozen dataclass: `topic`, `payload`, `sub_topic`, `timestamp`.

---

### 2b. Sub-topic Routing (ADR-025) — cosalette ≥ 0.3.0

#### What it replaces

Manual payload inspection and `if`/`return` multiplexing inside a single
`@ctx.on_command` handler.

#### Which apps benefit

- **●** velux, vito (direct — currently multiplex commands in one handler)
- **○** gas (potential future use)

#### Migration steps

1. Split the monolithic `@ctx.on_command` handler into separate handlers.
2. Add the sub-topic string to `@ctx.on_command("subtopic")`.
3. The default `@ctx.on_command` (no argument) handles the base topic.

**Before (velux2mqtt):**

```python
@ctx.on_command
async def handle_command(topic: str, payload: str) -> None:
    cal_params = _parse_calibrate(payload)
    if cal_params is not None:
        await _handle_calibration(cal_params)
        return
    command = parse_command(payload)
    await execute(command)
```

**After:**

```python
@ctx.on_command
async def handle_position(payload: str) -> None:
    command = parse_command(payload)
    await execute(command)

@ctx.on_command("calibrate")
async def handle_calibrate(payload: str) -> None:
    cal_params = json.loads(payload)
    await _handle_calibration(cal_params)
```

#### Breaking changes

None — additive. Unrouted commands still go to the default handler.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- Sub-topic routing is topic-level, not payload-level — consumers must publish to
  `{prefix}/{device}/command/calibrate`.
- The base `@ctx.on_command` handler receives commands that do **not** match any
  registered sub-topic.

---

### 3. Retry / Backoff (ADR-024) — cosalette ≥ 0.3.0

#### What it replaces

No built-in retry — telemetry functions either fail silently or crash the device task on
transient errors. Apps implement ad-hoc `try`/`except` with manual sleep.

#### Which apps benefit

- **●** airthings, caldates, gas, vito (direct — all poll external sources)

#### Migration steps

1. Add `retry=`, `retry_on=`, and optionally `backoff=` to the `@app.telemetry`
   decorator.
2. Remove any manual retry/sleep logic inside the telemetry function.
3. Optionally add `CircuitBreaker(threshold=N)` for sources with sustained outages.

**Before (airthings2mqtt):**

```python
@app.telemetry("airthings", interval=_poll_interval)
async def _telemetry(
    reader: AirthingsReaderPort, settings: Airthings2MqttSettings,
) -> dict[str, object]:
    reading = await reader.read(settings.device_mac)
    return {...}
```

**After:**

```python
@app.telemetry(
    "airthings", interval=_poll_interval,
    retry=3, retry_on=(BleConnectionError, BleTimeoutError),
)
async def _telemetry(
    reader: AirthingsReaderPort, settings: Airthings2MqttSettings,
) -> dict[str, object]:
    reading = await reader.read(settings.device_mac)
    return {...}
```

#### Breaking changes

None — additive. Telemetry functions without `retry=` behave identically to before.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- **`retry_on` defaults to `(OSError,)`** — this covers `TimeoutError` because it is a
  subclass of `OSError` since PEP 3151. Override explicitly if you need different
  exception types.
- **`ValueError` is NOT retried by default** — bugs should fail fast.
- **Retry counter is cumulative** across telemetry cycles, not reset each cycle.
- **Circuit breaker is opt-in:** `CircuitBreaker(threshold=5)` — add it for sources with
  sustained outages.
- **Retry is NOT available on `@app.command` or `@app.device`** — only `@app.telemetry`.
- Backoff strategies: `ExponentialBackoff` (default), `LinearBackoff`, `FixedBackoff`.

---

### 4. Lifespan-Yielded DI State (ADR-027) — cosalette ≥ 0.3.0

#### What it replaces

Module-level singleton with `global _state` pattern — fragile, hard to test, and
invisible to the DI container.

#### Which apps benefit

- **●** jeelink (direct — currently uses `global _state`)
- **○** gas, vito (potential — if they have shared state across devices)

#### Migration steps

1. Remove the `global _state` variable and `get_state()` accessor.
2. Change the lifespan context manager to `yield state` instead of `yield`.
3. Declare the state type as a parameter in telemetry/device functions — DI injects it.

**Before (jeelink2mqtt):**

```python
_state: SharedState | None = None
def get_state() -> SharedState:
    if _state is None: raise RuntimeError(...)
    return _state

@asynccontextmanager
async def _lifespan(ctx: AppContext) -> AsyncIterator[None]:
    global _state
    _state = SharedState(ctx.settings)
    yield
    _state = None
```

**After:**

```python
@asynccontextmanager
async def _lifespan(ctx: AppContext) -> AsyncIterator[SharedState]:
    state = SharedState(ctx.settings)
    yield state  # auto-registered in DI

@app.telemetry("sensor", interval=60)
async def sensor(state: SharedState) -> dict[str, object]:
    return state.latest_reading()
```

#### Breaking changes

None — additive. `yield` (without a value) still works.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- The yielded value is auto-registered in DI by `type(value)` — ensure the type is
  unique.
- **Not available in `on_configure` hooks** — lifespan runs after `on_configure`.

---

### 5. Adapter Health Check (ADR-028) — cosalette ≥ 0.3.0

#### What it replaces

No built-in health monitoring — adapter failures are silent until telemetry starts
failing. No automatic offline/online status management.

#### Which apps benefit

- **●** airthings, jeelink, velux, vito (direct — all have adapters with external
  dependencies)

#### Migration steps

1. Add `async def health_check(self) -> bool` to the adapter class.
2. No registration needed — the framework detects `HealthCheckable` via `isinstance()`
   after adapter lifecycle entry.
3. Optionally tune `App(health_check_interval=30.0)` (default 30s).

**Before (airthings2mqtt):**

```python
class BleakAirthingsReader:
    async def read(self, mac: str) -> Reading: ...
```

**After:**

```python
class BleakAirthingsReader:
    async def read(self, mac: str) -> Reading: ...

    async def health_check(self) -> bool:
        try:
            scanner = BleakScanner()
            await asyncio.wait_for(scanner.discover(timeout=5), timeout=10)
            return True
        except Exception:
            return False
```

#### Breaking changes

None — additive. Adapters without `health_check()` are not monitored.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- `HealthCheckable` is a `@runtime_checkable` Protocol — **no registration or
  inheritance needed**, just implement the method.
- Default interval is **30s**, timeout per probe is **interval / 2**.
- Failed check → devices depending on the adapter go "offline", recovery → "online".
- Exceptions inside `health_check()` are **caught and treated as failure** — never
  crashes the app.
- `health_check()` **must be truly async** (do real I/O, not sync-wrapped).
- `health_check_interval=None` **disables** health checking.
- **Startup check runs before devices** — devices can start in "offline" state.
- Health checks are **informational only** — telemetry continues even when offline.
- **Adapter-to-device mapping** uses DI introspection.
- **Log deduplication:** first failure = WARNING, consecutive = DEBUG, recovery = INFO.

---

### 6. Auto-Restart (ADR-029) — cosalette ≥ 0.3.0

> **Prerequisite:** Epic 5 (Health Check). Auto-restart uses the health check
> infrastructure to detect failures.

#### What it replaces

No built-in restart — adapter failures require manual intervention or external process
supervisors.

#### Which apps benefit

- **●** airthings, jeelink, velux, vito (direct — all have adapters that can fail
  transiently)

#### Migration steps

1. Ensure the adapter implements `health_check()` (Epic 5).
2. Configure restart parameters on the `App` constructor.
3. Optionally opt out specific adapters with `restartable: ClassVar[bool] = False`.

```python
app = App(
    restart_after_failures=5,   # consecutive health failures before restart
    max_restarts=3,             # max restart attempts per adapter
    restart_cooldown=5.0,       # seconds between restarts
    sustained_health_reset=300.0,  # seconds of health before resetting counter
)
```

#### Breaking changes

None — additive. Default behavior is no auto-restart (all parameters default to
disabled).

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- Uses **cancel + recreate** pattern for device tasks — in-flight telemetry is
  cancelled.
- Opt-out per adapter: `restartable: ClassVar[bool] = False` on the adapter class.
- `sustained_health_reset` resets the restart counter after sustained healthy operation.

---

### 7. Cron Scheduling / sleep_until (ADR-032) — cosalette ≥ 0.3.0

#### What it replaces

Fixed-interval polling for day-aligned data — wastes cycles overnight and misses the
optimal publish window.

#### Which apps benefit

- **●** caldates (direct — publishes calendar data at fixed times of day)

#### Migration steps

1. Convert `@app.telemetry` with `interval=` to `@app.device` with a manual loop.
2. Use `await ctx.sleep_until(target, tz=None)` for wall-clock aligned sleep.
3. Alternatively, use `schedule=` on `@app.telemetry` for cron-based scheduling.

**Before (caldates2mqtt):**

```python
@app.telemetry("calendar", interval=7200)
async def calendar() -> dict: ...
```

**After:**

```python
@app.device("calendar")
async def calendar(ctx: DeviceContext) -> None:
    while not ctx.shutdown_requested:
        events = await read_events()
        await ctx.publish_state({"events": events})
        await ctx.sleep_until(time(6, 0))  # next check at 06:00
```

**Alternative (cron):**

```python
@app.telemetry("calendar", schedule="0 0 6,18 * * ?")
async def calendar() -> dict:
    return {"events": await read_events()}
```

#### Breaking changes

None — additive. `interval=` continues to work.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- `schedule=` uses **Quartz cron format** (6–7 fields, not POSIX 5-field).
- `schedule=` and `interval=` are **mutually exclusive** — specifying both raises
  `ValueError`.
- `CronSchedule(expression)` class available for programmatic use.
- `sleep_until` respects DST transitions when `tz=` is provided.

---

### 8. Sub-Entity (ADR-031) — cosalette ≥ 0.3.0

#### What it replaces

Implicit state machine values for sub-entity availability — publishing calibration
status to the main state topic with no separate availability tracking.

#### Which apps benefit

- **●** velux, vito (direct — have logical sub-entities like calibration, zones)
- **○** jeelink (potential — multiple sensor types per device)

#### Migration steps

1. Identify logical sub-entities (calibration, zones, modes, etc.).
2. Wrap sub-entity logic in `async with ctx.sub_entity("name") as sub:`.
3. Use `sub.publish_state()` and `sub.on_command()` instead of the parent context.

**Before (velux2mqtt):**

```python
# Calibration state published to main state topic
await ctx.publish_state({"calibration": "measuring", ...})
```

**After:**

```python
async with ctx.sub_entity("calibrate") as cal:
    await cal.publish_state({"step": "measuring"})
    # calibrate/availability auto-managed
```

#### Breaking changes

None — additive. Existing state publishing continues to work.

#### Minimum version bump

`cosalette>=0.3.0`

#### Gotchas

- **Single-level only** — sub-entities cannot be nested.
- Topics follow the pattern: `{prefix}/{device}/{sub}/state`,
  `{prefix}/{device}/{sub}/availability`.
- `SubEntityContext` provides `publish_state()`, `publish()`, and `on_command()`.
- **Availability is auto-published** — online on enter, offline on exit.
- **Retained state is cleared** on context exit.

---

## Per-App Consolidated Checklists

### airthings2mqtt

- [ ] **Epic 3 — Retry/backoff:** Add
      `retry=3, retry_on=(BleConnectionError, BleTimeoutError)` to `@app.telemetry`.
- [ ] **Epic 5 — Health check:** Add `async def health_check(self) -> bool` to the BLE
      adapter (BleakScanner probe).
- [ ] **Epic 6 — Auto-restart:** Configure
      `App(restart_after_failures=5, max_restarts=3)` for BLE adapter recovery.
- [ ] ○ **Epic 1 — on_configure:** Evaluate if device registration can move to
      `@app.on_configure`.
- [ ] ○ **Epic 2a — ctx.commands():** Evaluate if command handling can use
      `ctx.commands()`.

### caldates2mqtt

- [ ] **Epic 1 — on_configure:** Move `CalDates2MqttSettings()` instantiation and device
      registration into `@app.on_configure`.
- [ ] **Epic 2a — ctx.commands():** Replace manual queue-based command handling with
      `ctx.commands()`.
- [ ] **Epic 3 — Retry/backoff:** Add retry to calendar fetch telemetry for transient
      HTTP errors.
- [ ] **Epic 7 — sleep_until:** Convert interval-based polling to `ctx.sleep_until()` or
      `schedule=` for day-aligned fetches.

### gas2mqtt

- [ ] **Epic 1 — on_configure:** Move settings access into `@app.on_configure`.
- [ ] **Epic 2a — ctx.commands():** Replace manual command queue with `ctx.commands()`.
- [ ] **Epic 3 — Retry/backoff:** Add retry to gas telemetry for transient I/O errors.
- [ ] ○ **Epic 2b — Sub-topic routing:** Evaluate if command types warrant sub-topic
      routing.
- [ ] ○ **Epic 4 — Lifespan yield:** Evaluate if shared state across devices would
      benefit from lifespan yield.

### jeelink2mqtt

- [ ] **Epic 4 — Lifespan yield:** Replace `global _state` / `get_state()` with
      `yield state` in lifespan.
- [ ] **Epic 5 — Health check:** Add `health_check()` to the serial port adapter.
- [ ] **Epic 6 — Auto-restart:** Configure auto-restart for serial port adapter
      recovery.
- [ ] ○ **Epic 8 — Sub-entity:** Evaluate if multiple sensor types per device warrant
      sub-entities.

### velux2mqtt

- [ ] **Epic 1 — on_configure:** Move device registration into `@app.on_configure`.
- [ ] **Epic 2a — ctx.commands():** Replace manual command handling with
      `ctx.commands()`.
- [ ] **Epic 2b — Sub-topic routing:** Split `handle_command` into per-sub-topic
      handlers (`@ctx.on_command("calibrate")`).
- [ ] **Epic 5 — Health check:** Add `health_check()` to the KLF200 adapter.
- [ ] **Epic 6 — Auto-restart:** Configure auto-restart for KLF200 adapter recovery.
- [ ] **Epic 8 — Sub-entity:** Wrap calibration logic in `ctx.sub_entity("calibrate")`.

### vito2mqtt

- [ ] **Epic 2a — ctx.commands():** Replace `asyncio.Queue` + `wait_for` loop with
      `async for cmd in ctx.commands()`.
- [ ] **Epic 2b — Sub-topic routing:** Split command handlers by sub-topic if
      applicable.
- [ ] **Epic 3 — Retry/backoff:** Add retry to Viessmann API telemetry for transient
      errors.
- [ ] **Epic 5 — Health check:** Add `health_check()` to the Viessmann adapter.
- [ ] **Epic 6 — Auto-restart:** Configure auto-restart for Viessmann adapter recovery.
- [ ] **Epic 8 — Sub-entity:** Use sub-entities for heating zones or DHW circuits.
- [ ] ○ **Epic 4 — Lifespan yield:** Evaluate if shared adapter state should use
      lifespan yield.

---

## Version Bump Instructions

Update each app's `pyproject.toml` to require cosalette ≥ 0.3.0:

```toml
[project]
dependencies = [
    "cosalette>=0.3.0",
]
```

If the app uses optional extras, ensure the base dependency is bumped:

```toml
[project.optional-dependencies]
dev = [
    "cosalette[dev]>=0.3.0",
]
```

Run `uv lock` after updating to regenerate the lock file.

---

## Notes for Implementer

1. **Update framework reference:** The cosalette-apps monorepo's
   `cosalette-framework-reference.instructions.md` needs updating to match the new
   framework version (0.2.x API surface).

2. **Verify examples against actual code:** The before/after examples above are
   illustrative — verify against actual app code when migrating. Variable names, import
   paths, and settings classes may differ.

3. **Adopt features incrementally:** Each epic is independent, with one exception:
   **Epic 6 (Auto-restart) requires Epic 5 (Health Check)**. All other features can be
   adopted in any order.

4. **Testing:** Each migration should be accompanied by updated tests. The framework's
   test utilities (`cosalette.testing`) provide fakes for health check, commands, and
   sub-entities.

5. **Rollback safety:** All features are additive — no existing behavior changes. If a
   migration causes issues, simply remove the new decorator arguments or revert to the
   previous pattern.
