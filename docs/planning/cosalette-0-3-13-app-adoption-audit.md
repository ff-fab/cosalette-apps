# cosalette 0.3.13 App Adoption Audit

**Date:** 2026-05-03
**Status:** Complete
**Scope:** All non-jeelink apps after workspace-wide cosalette `>=0.3.13` bump (cap-lkn)
**Reference:** [jeelink2mqtt simplification doc](jeelink2mqtt-main-simplification.md)

---

## Summary Table

| App | Recommendation | Features to consider | Existing beads |
|-----|---------------|----------------------|----------------|
| airthings2mqtt | **Refactor** | `triggerable=True` on `@app.telemetry` | cap-clg (open) |
| caldates2mqtt | **No-op** | Already fully 0.3.13-native | — |
| gas2mqtt | **Refactor** | Replace `lifespan=` with `@app.state` | — |
| suncast | **Keep** | Minor: `@app.state` for SVG cross-device state | — |
| velux2mqtt | **Keep** | `@app.on_configure` already used; see workspace-35p | workspace-35p (close) |
| vito2mqtt | **Keep** | Eager `store=` minor smell; imperative registration appropriate | workspace-485 (narrow) |
| wallpanel-control | **No-op** | App is a stub; workspace-ds8 implementation must apply 0.3.13-native patterns from day one | workspace-ds8 (update) |

---

## Per-App Notes

### airthings2mqtt — Refactor

**Evidence:** `apps/airthings2mqtt/packages/src/airthings2mqtt/main.py`

Current state: single `@app.telemetry("airthings", interval=setting_ref("poll_interval"))`,
25-minute BLE polling cycle. Already has `summary=` and `state_model=` (contracts).
No `triggerable=True`.

**Opportunity:** Add `triggerable=True` so HomeAssistant automations or users can
request an immediate BLE read via `airthings2mqtt/airthings/set`. Inject
`cosalette.TriggerPayload` to distinguish triggered vs. scheduled runs. Low
complexity: single sensor, no multi-device.

This is exactly the scope of **cap-clg** — confirmed still relevant.

**Other features:** No additional 0.3.13 adoption needed. `health_check_interval` on
`App(...)` is already applied at the framework level; no per-device override needed.

---

### caldates2mqtt — No-op

**Evidence:** `apps/caldates2mqtt/packages/src/caldates2mqtt/main.py`

Already uses:

- `name=_calendar_map` — multi-device declarative pattern from settings
- `schedule=lambda cal: cal.schedule` — per-device cron schedule
- `triggerable=True` + `cosalette.TriggerPayload` with payload-driven `entries`/`days`
- `cosalette.App` adapters dict

This is the **reference implementation** for the 0.3.13 feature set among these apps.
No changes warranted.

---

### gas2mqtt — Refactor

**Evidence:** `apps/gas2mqtt/packages/src/gas2mqtt/main.py`

Current state: uses `lifespan=_gas_lifespan` to create and inject the shared
`GasCounterState`. The lifespan is an `@asynccontextmanager` that constructs the
state from settings, then `yield`s it for DI injection into `gas_counter` and
`update_consumption` handlers.

**Opportunity:** Migrate to `@app.state` (available in 0.3.13):

```python
@app.state
async def gas_counter_state(settings: Gas2MqttSettings) -> AsyncIterator[GasCounterState]:
    store_backend = _make_store(settings)
    device_store = DeviceStore(store_backend, "gas_counter")
    state = make_gas_counter(settings, device_store, logging.getLogger("gas2mqtt.state"))
    yield state
```

Remove `lifespan=_gas_lifespan` from `App(...)`. The framework injects `GasCounterState`
by type into any handler that declares it. Eliminates the `_gas_lifespan` top-level
function, reduces `create_app()` complexity.

**Caution:** `@app.state` teardown order is LIFO. Only one state object here, so
ordering is not a concern. The `yield` form supports async teardown.

---

### suncast — Keep

**Evidence:** `apps/suncast/packages/src/suncast/app.py`

Uses `lifespan=_lifespan` for the HTTP server lifecycle. This is a **genuine
side-effect lifespan** (starting/stopping aiohttp server), not a state injection
use case. `lifespan=` remains the correct API here; `@app.state` is for DI injection,
not side-effect orchestration.

Uses `init=_build_pipeline` for per-device `PipelineState` — appropriate; `init=`
factories inject per-device (not app-scoped) state.

**Minor opportunity:** `_latest_svg: list[str | None] = [None]` is a module-level
mutable singleton used to share the latest SVG between the telemetry handler and
the HTTP server callback. With `@app.state`, a `SvgState` dataclass could hold this
more explicitly. Low priority: the current workaround is contained and tested.

---

### velux2mqtt — Keep

**Evidence:** `apps/velux2mqtt/packages/src/velux2mqtt/main.py`

Already uses `@app.on_configure` to register one `make_cover()` device per cover
config entry. This is exactly the multi-device pattern recommended for complex
conditional logic where each device needs a **different closure** (distinct GPIO
pins, calibration state machine per cover).

`@app.on_configure` + `app.add_device` loop is appropriate here. The `name=callable`
(dict-name) pattern would only simplify this if all covers shared one handler; they
don't — each cover is its own closure factory.

**workspace-35p verdict:** STALE. The task asked to move eager settings to
`@app.on_configure` — velux2mqtt already does this. See Beads Updates below.

---

### vito2mqtt — Keep

**Evidence:** `apps/vito2mqtt/packages/src/vito2mqtt/main.py`

Uses imperative `register_telemetry(app)`, `register_commands(app)`,
`register_legionella(app)` functions to handle a large number of signal-group
devices. This is the right pattern for complex multi-group registration that
doesn't fit a single dict-name lambda.

Minor code smell: `store=JsonFileStore(resolve_store_path())` is eagerly evaluated
at module import time, whereas gas2mqtt correctly defers with `store=_make_store`
(callable). Not a 0.3.13 adoption issue — pre-existing.

No `lifespan=` required. No `@app.state` needed. Already uses contracts metadata
(`summary=`, `behavior=`, `effects=`) in the telemetry and command registrations.

**workspace-485 verdict:** 8 of 10 original dependencies done. The only remaining
live blocker is workspace-658 (gas retry/backoff). workspace-35p is closed. See Beads
Updates below.

---

### wallpanel-control — No-op

**Evidence:** `apps/wallpanel-control/packages/src/wallpanel_control/main.py` —
`raise SystemExit("Not yet implemented.")`

App is a stub; there is no existing code to refactor or keep. The current state
warrants no changes (no-op). When workspace-ds8 implements the app, it must apply
0.3.13-native patterns from day one rather than retrofitting them later.

**0.3.13-native patterns to apply at build time (workspace-ds8 guidance):**

| Concern | Pattern |
|---------|---------|
| Status polling (brightness, screen on/off) | `@app.telemetry("status", interval=..., triggerable=True)` |
| On-demand status refresh via MQTT | `triggerable=True` on status telemetry |
| Shared SSH connection state | `@app.state` to hold SSH adapter or cache |
| Brightness set / screen on-off / power commands | `@app.command("brightness")` etc. |
| WoL command | `@app.command("wake")` |
| Adapter isolation | Ports & Adapters with `app.adapter(SshPort, ..., dry_run=...)` |

The SSH-offline-as-non-error opportunity (workspace-rpe item 1) is still a gap in
0.3.13. The workaround is returning `None` from port methods to signal unavailability,
handled in the telemetry handler. Document this in the implementation.

---

## Beads Updates

### cap-clg — `airthings2mqtt: add triggerable=True`

**Action:** Verified still relevant. Notes updated via `bd update cap-clg`.
airthings2mqtt does not yet have `triggerable=True`. Work is well-scoped, depends on
`cap-lkn` (done). No changes to acceptance criteria needed.

### workspace-ds8 — `wallpanel-control` epic

**Action:** Notes updated via `bd update workspace-ds8`.
The 0.3.13 feature set that helps this epic: `@app.state` for shared SSH state,
`triggerable=True` on status telemetry, `@app.command` for each control action.
Acceptance criteria unchanged — scope is still "implement the app".

### workspace-35p — `velux: move eager settings to @app.on_configure`

**Action:** CLOSED via `bd close workspace-35p`.
velux2mqtt already uses `@app.on_configure` to register covers. The task described
the correct fix; it was applied during the Epic 3 migration. No remaining work.

### workspace-485 — `commands: update tests for Epic 3 migration`

**Action:** Narrowed and updated via `bd update workspace-485`.
8 of 10 original dependencies are done. workspace-35p is closed/stale (see above)
and no longer a live blocker. The sole remaining live blocker is:
- `workspace-658` — gas retry/backoff (still open)

Remaining test work reduces to: validate gas retry path once workspace-658 is
complete. The original broad scope (gas + velux + vito on_configure, ctx.commands(),
sub-entities) is largely done. Acceptance criteria narrowed to gas retry tests only.

### workspace-rpe — `Write framework-opportunities.md`

**Action:** Notes updated via `bd update workspace-rpe`.
Of the four opportunities listed in the description:

| # | Opportunity | 0.3.13 Status |
|---|-------------|---------------|
| 1 | SSH timeout as non-error state | **Still a gap** — no framework support; workaround: return `None` from port method |
| 2 | Shared state across device handlers | **Resolved** — `@app.state` in 0.3.13 provides app-scoped DI injection |
| 3 | Optimistic state after command | **Still a gap** — no cross-device state channel; workaround: module-level shared state |
| 4 | Command validation/parsing (Pydantic payload models) | **Still a gap** — handlers receive raw `str`; `payload_model=` is metadata only |

The `framework-opportunities.md` doc should be written with items 1, 3, and 4 as
remaining opportunities and item 2 marked as resolved.

---

## Next Sequence

Recommended implementation order after this audit:

1. **cap-clg** — `airthings2mqtt` triggerable telemetry. Low risk, self-contained,
   well-specified. One-file change to `main.py`.

2. **gas2mqtt `@app.state` migration** — Replace `lifespan=_gas_lifespan` with
   `@app.state`. Medium complexity; improves readability of `main.py`.

3. **workspace-658** — gas retry/backoff. Prerequisite for closing workspace-485.

4. **workspace-485** (narrowed) — Gas retry test coverage after workspace-658.

5. **workspace-ds8** — wallpanel-control implementation. Largest item; can use
   caldates2mqtt as style reference and this audit's pattern table.

6. **workspace-rpe** — Write `framework-opportunities.md` using the resolved/remaining
   table above. Depends on cap-0oc being complete (this document).
