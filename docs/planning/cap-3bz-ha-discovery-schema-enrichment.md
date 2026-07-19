# cap-3bz — HA Discovery Schema Enrichment

**Date:** 2026-07-19
**Status:** Planning
**Task:** [cap-3bz] Enrich remaining app schemas with consumer metadata for HA discovery

---

## Objective

Provide `x-cosalette-consumer` (device_class, unit, state_class, icon) and
`x-cosalette-app` annotations in each app's `schema.yaml` so that
[cosalette-hass-discovery](https://github.com/ff-fab/cosalette-hass-discovery)
can auto-generate HA sensor configurations. **airthings2mqtt** is the completed
reference. Six remaining apps.

Pre-requisite for several channels: the telemetry handler must declare
`state_model=<TypedModel>` so `cosalette schema init` exports typed properties
rather than `type: object`.

---

## Per-App Analysis

### 1. gas2mqtt — **HIGH VALUE** (3 channels)

| Channel | Current | Gap | HA target |
|---------|---------|-----|-----------|
| `gas_counterState` | `state_model=GasCounterState` ✓ typed | Add `x-cosalette-consumer` to the `total_m3` / `delta_m3` / `rate_m3h` properties in schema.yaml | `device_class: gas`, `unit: m³`, `state_class: total_increasing` |
| `temperatureState` | returns `{"temperature": float}` — no `state_model` | **Add `state_model=TemperatureReading` Pydantic model** (one field: `temperature: float`) + annotate schema | `device_class: temperature`, `unit: °C`, `state_class: measurement` |
| `magnetometerState` | debug-only (`enabled=enable_debug_device`) | **Not applicable** — debug/calibration telemetry, no meaningful HA entity | Document as N/A |

**Phase 2 work:** create `TemperatureReading` model, wire it, regenerate schema, annotate.

---

### 2. vito2mqtt — **HIGH VALUE** (5 channels)

All signal-group telemetry handlers (`make_telemetry_handler`) return
`dict[str, object]` — no typed model. vito has 5 channels: `hot_water`,
`heating_radiator`, `heating_floor`, `system`, `outdoor`.

**Challenge:** each group contains many heterogeneous signals (temperatures,
schedules, error histories). A single `state_model` per group would be very
large, and the cosalette `OnChange(threshold=...)` dict-key strategy requires
the dict to be stable.

**Options:**

**Option A — One typed Pydantic model per signal group**
Create e.g. `HotWaterState`, `SystemState` etc. (each ~5–15 fields). Full schema
typing; enables individual property annotation. High effort (~5 models × 10+
fields). Each must match the exact dict keys returned by the signal group.

**Option B — Annotate the schema manually without state_model**
Keep handlers returning dicts. Add `x-cosalette-consumer` annotations
per-property directly in `schema.yaml` (manually maintained, not regenerated).
Medium effort; loses schema init→check round-trip validation benefit.

**Option C — Typed models for the most valuable groups only**
Prioritise `outdoor` (outdoor_temperature → single HA sensor) and
`hot_water` (hot_water_setpoint — the one writable by HA). Leave the rest as
N/A for this iteration with a follow-up.

**Recommendation: Option C**, then extend to remaining groups in a follow-up.
`outdoor` telemetry is a single `float` (outdoor_temperature) — trivially typed.
`hot_water_setpoint` is already a writable command (not telemetry) — no schema
work needed.

---

### 3. wallpanel-control — **MEDIUM VALUE** (2 channels)

`display/state` and `system/action/state` already have `state_model=DisplayState`
and `state_model=SystemActionState` on the **command** routers (not telemetry).
These are state-reply schemas, not periodic telemetry. The schema.yaml already
emits typed properties. Gap is only `x-cosalette-consumer` annotations.

**Work:** Add `x-cosalette-consumer` to the existing typed properties in
`schema.yaml`. No src/ changes needed.

- `display/state.state` → `device_class: switch`
- `system/action/state.accepted` → no direct HA mapping (N/A, document)

---

### 4. caldates2mqtt — **MEDIUM VALUE** (1 channel, dynamic)

`calendar` handler returns `dict[str, object]` with dynamic keys (one per
calendar entry). The `name=_calendar_map` pattern creates one MQTT topic per
calendar at runtime — the schema.yaml has 1 channel template.

**Challenge:** HA discovery for date-event payloads is unusual. HA doesn't
have a standard `device_class: calendar`. The payload would need to be a
`sensor` with `state_class: measurement` (number of days until next event),
or a `binary_sensor` (event active today), or a text `sensor`. This is
app-specific logic with no standard HA mapping.

**Recommendation: N/A for now** — document rationale. The payload schema is
`dict[str, object]` (list of events) rather than a scalar HA can use directly.
Adding a typed `CalendarEventList` model would help schema quality but not
enable standard HA discovery without a custom template. Flag as a future
enhancement once the HA discovery library supports event-list payloads.

---

### 5. suncast — **LOW VALUE** (1 channel)

`_shadow_handler` returns `None` — it publishes via
`state.output_manager.deliver(svg, {}, ctx)` (SVG data), not via the standard
cosalette state mechanism. The schema.yaml has `shadowState` but the handler
bypasses standard publishing.

**Recommendation: N/A** — suncast publishes an SVG image payload, not a scalar
HA-measurable value. No standard `x-cosalette-consumer` mapping exists.
Document as "N/A — SVG output not an HA sensor type".

---

### 6. velux2mqtt — **HIGH VALUE** (1 channel: cover position)

`cover_deviceState` — the cover device publishes position (0–100%), tilt, and
state (opening/closing/stopped). HA has `cover` as a first-class device type.

**Challenge:** `cover_device` is an `AsyncIterator` device (not telemetry), so
`state_model=` is set differently. Let me verify the schema channel shape and
whether a typed Pydantic model exists.

Current: `cover_deviceState` has 1 channel with no `x-cosalette-consumer`.
The cover state payload has known keys (`position`, `tilt`, `state`,
`cover_name`). A `CoverState` Pydantic model would fit.

**Work:** Create `CoverState` model, add `state_model=CoverState` to
`cover_device`, regenerate schema, annotate with HA cover consumer metadata.

---

## Summary Table

| App | Channels | Phase 2 (state_model)? | x-cosalette-consumer | HA value | Priority |
|-----|----------|------------------------|----------------------|----------|----------|
| **gas2mqtt** | gas_counter✓, temperature✗, magnetometer✗ | TemperatureReading model | gas_counter + temperature | HIGH | **1** |
| **velux2mqtt** | cover_device✗ | CoverState model | position/tilt/state | HIGH | **1** |
| **wallpanel-control** | display/system ✓ (command state) | None needed | limited (display switch) | MEDIUM | **2** |
| **vito2mqtt** | 5 groups, all `dict` | Option C: OutdoorState model | outdoor_temperature | MEDIUM | **2** |
| **caldates2mqtt** | 1 dynamic | CalendarEventList (optional) | N/A (document) | N/A | — |
| **suncast** | 1 SVG | None | N/A (document) | N/A | — |

---

## Proposed Delivery Plan

### Phase 1 — High-value apps (one PR each)
1. **gas2mqtt** — add `TemperatureReading(temperature: float)` Pydantic model; wire `state_model=TemperatureReading`; regenerate schema; add `x-cosalette-consumer` to gas_counter and temperature channels; add guard test mirroring airthings pattern.
2. **velux2mqtt** — add `CoverState` Pydantic model; wire `state_model=CoverState`; regenerate schema; annotate `cover_deviceState` with HA cover metadata; add guard test.

### Phase 2 — Medium-value apps (one PR)
3. **wallpanel-control** — no src change; annotate schema.yaml display/system channels; add guard tests.
4. **vito2mqtt** — add `OutdoorState(outdoor_temperature: float)` model; wire; regenerate; annotate outdoor channel; add guard test. Remaining groups: manual annotation or follow-up.

### Phase 3 — N/A documentation (single small PR)
5. **caldates2mqtt + suncast** — add `x-cosalette-not-applicable: reason:` to their schema.yaml channels; document in app READMEs.

---

## Open Questions

1. **vito2mqtt Option A vs C:** Should we do full typed models for all 5 groups
   (Option A) or just `outdoor` + `hot_water` for this sprint (Option C)?
   → Recommend C for now; each group model is ~15 fields and benefits from a
   dedicated investigation.

2. **velux cover device_class:** does cosalette-hass-discovery support
   `device_class: cover` or does it need `position_topic` / `tilt_topic`
   separately?
   → Confirm before implementing Phase 1.2.

3. **Guard test scope:** should the guard test be a `schema check` CI assertion
   (like airthings has in CI) or a unit test that deserializes the consumer
   metadata?

---

## Next Step

Review this plan and confirm:
- Phase 1 priority order (gas2mqtt first, then velux, or together?)
- vito Option A vs C
- Whether to split into per-app PRs or batch Phase 1 into one PR
