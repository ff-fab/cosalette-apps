## Epic cap-3bz Complete: Phase 2 — wallpanel-control + vito2mqtt HA Discovery

Enriched the `wallpanel-control` and `vito2mqtt` AsyncAPI schemas with
`x-cosalette-consumer` metadata so `cosalette schema ha-discovery` emits Home
Assistant MQTT discovery payloads. vito2mqtt Option A typed **all 7** telemetry
signal groups; HA sensors are surfaced for the two telemetry-only groups (11
sensors), with the four shared telemetry+command groups blocked by a framework
`oneOf` traversal gap now tracked as cap-075. Delivered on PR #181 (CI green).

**Files created/changed:**
- apps/wallpanel-control/docs/schema.yaml (annotated `displayState`)
- apps/wallpanel-control/packages/tests/integration/test_schema_discovery.py (new)
- apps/vito2mqtt/docs/schema.yaml (regenerated to typed properties + annotations)
- apps/vito2mqtt/packages/src/vito2mqtt/devices/telemetry_models.py (new)
- apps/vito2mqtt/packages/src/vito2mqtt/_registration.py (wired `state_model` per group)
- apps/vito2mqtt/packages/tests/integration/test_schema_discovery.py (new)

**Functions/classes created/changed:**
- `ErrorHistoryEntry`, `OutdoorState`, `HotWaterState`, `BurnerState`,
  `HeatingRadiatorState`, `HeatingFloorState`, `SystemState`, `DiagnosisState`
  frozen dataclasses (new telemetry_models module)
- `GROUP_STATE_MODELS` mapping (signal-group key → state_model)
- `configure_app()` — added `state_model=GROUP_STATE_MODELS[group]` to the
  telemetry registration loop

**Tests created/changed:**
- wallpanel-control `TestHaDiscoveryGeneration` — 2 sensors (display state, brightness)
- vito2mqtt `TestHaDiscoveryGeneration` — golden set of 11 sensors (outdoor + burner),
  device grouping, per-sensor config fields, bare-counter (no unit) case

**Review Status:** APPROVED — `task pre-pr` all gates green; PR #181 CI all-green.

**Framework gap filed:** cap-075 (ha-discovery should descend into `oneOf`/`anyOf`
payload variants) — unblocks ~9 shared-group sensors (hot_water / heating_radiator
/ heating_floor / system) once landed.

**Git Commit Messages:**

```
feat(wallpanel-control): enrich schema for HA discovery

- Annotate displayState.state and brightness_percent with x-cosalette-consumer
- Add x-cosalette-app so ha-discovery emits sensor entities
- Add schema discovery guard test (integration)
```

```
feat(vito2mqtt): type telemetry payloads and enrich for HA discovery

- Add frozen state_model dataclasses for all 7 signal groups
- Wire state_model per group so schema emits typed payload properties
- Annotate outdoor and burner fields with x-cosalette-consumer
- Regenerate schema; add schema discovery guard test (11 sensors)
```
