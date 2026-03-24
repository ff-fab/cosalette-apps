# Framework Opportunities

velux2mqtt already uses cosalette's core device model (`@app.device` via
`app.add_device()`), adapter registration, settings, and health reporting. This page
identifies cosalette features that could add value but are **not yet adopted**, along with
an assessment of when each would be worth implementing.

---

## Currently Used

| cosalette Feature          | How velux2mqtt Uses It                                  |
| -------------------------- | ------------------------------------------------------- |
| `App` composition root     | `main.py` --- registers adapters and cover devices      |
| `app.add_device()`         | One device per configured cover, created in a loop      |
| `DeviceContext`            | Command handling (`on_command`), state publishing, shutdown-aware sleep |
| Adapter registry           | `GpioSwitchPort` -> `GpiozeroAdapter` / `FakeGpio`     |
| `Settings` subclass        | `Velux2MqttSettings` with Pydantic validation           |
| Health reporter            | Heartbeats, per-device availability, LWT (automatic)    |
| Error isolation            | Per-device error topics (automatic)                     |
| Graceful shutdown          | `ctx.shutdown_requested` + `ctx.sleep()` in cover loop  |

---

## Not Yet Adopted

### Persistence (`DeviceStore`)

**Feature:** `store=JsonFileStore()` + `DeviceStore` DI for per-device state persistence.

**Opportunity:** Persist the cover's last known position across restarts. Currently,
velux2mqtt homes (moves to an endpoint) on every startup because it has no memory of
where the cover was. With persistence:

- Store `position` after each move
- On startup, load the last known position and skip homing if it was recently saved
- Still home if the position is stale (e.g., after a long power outage)

**When to adopt:** When avoiding unnecessary homing on restarts becomes a user priority.
This is particularly relevant for window covers where a full close-open cycle is noisy and
time-consuming.

**Effort:** Low. Add `store=JsonFileStore("state.json")` to `App()`, inject `DeviceStore`
in the cover device, save position after each move.

---

### Publish Strategy (`OnChange`)

**Feature:** `publish=OnChange(threshold=1)` to suppress duplicate state publications.

**Opportunity:** The cover device currently publishes position after every movement step.
For small moves where the rounded position doesn't change, this generates redundant MQTT
messages. `OnChange` would suppress them.

**When to adopt:** Low priority. Cover movements are infrequent (user-initiated), so
publish volume is already low. This would matter more if velux2mqtt added periodic
position reporting.

**Effort:** Minimal. However, this would require switching from `@app.device` to
`@app.telemetry` or manually integrating the strategy, since `OnChange` is a telemetry
decorator feature.

---

### Signal Filters

**Feature:** `Pt1Filter`, `MedianFilter`, `OneEuroFilter` for noisy sensor smoothing.

**Opportunity:** Not applicable. velux2mqtt has no sensor input --- position is calculated
from travel time, not measured. There is no noisy signal to filter.

**When to adopt:** Not applicable unless a future version adds position feedback sensors.

---

### Telemetry Coalescing Groups

**Feature:** `group="name"` for synchronized multi-device polling.

**Opportunity:** Not applicable. Cover devices are event-driven (command-based), not
periodic polling devices. Each cover operates independently on its own command stream.

**When to adopt:** Not applicable.

---

### Deferred Interval Resolution

**Feature:** `interval=lambda s: s.my_interval` for settings-dependent intervals.

**Opportunity:** Not applicable. Cover devices use `@app.device` (full lifecycle), not
`@app.telemetry` (periodic polling). There are no intervals to configure.

**When to adopt:** Not applicable.

---

### `init=` Callback

**Feature:** Per-device state factory injected via DI.

**Opportunity:** The current `make_cover()` closure pattern creates per-device state
(`PositionTracker`, `DriftCompensator`, `CalibrationStateMachine`) inside the device
function body. The `init=` callback could extract this into a factory function, making the
state setup more explicit and separately testable.

**When to adopt:** Low priority. The current closure pattern works well and is already
tested. The `init=` pattern would be more valuable if the state setup became complex
enough to warrant its own test suite.

**Effort:** Low. Factor `make_cover_state()` -> state dataclass, wire via `init=` kwarg.

---

### `@app.command` Decorator

**Feature:** Declarative command handler with automatic dispatch.

**Opportunity:** The current `@ctx.on_command` pattern inside `@app.device` gives full
control over command parsing and state management. The `@app.command` decorator is simpler
but lacks the ability to maintain per-device state between commands (position tracker,
drift compensator).

**When to adopt:** Not recommended. The full-lifecycle `@app.device` pattern is the
correct choice for covers because they need persistent state, multi-step GPIO sequences,
and startup homing --- none of which fit the stateless `@app.command` model.

---

## Summary

| Feature                    | Value for velux2mqtt | Effort | Recommendation    |
| -------------------------- | -------------------- | ------ | ----------------- |
| Persistence (DeviceStore)  | High                 | Low    | Adopt when homing becomes a pain point |
| OnChange publish strategy  | Low                  | Low    | Defer             |
| Signal filters             | None                 | ---    | Not applicable    |
| Coalescing groups          | None                 | ---    | Not applicable    |
| Deferred intervals         | None                 | ---    | Not applicable    |
| `init=` callback           | Low                  | Low    | Defer             |
| `@app.command`             | None                 | ---    | Not recommended   |

The most impactful next step is **persistence** --- it directly improves user experience
by eliminating unnecessary homing cycles on restart.
