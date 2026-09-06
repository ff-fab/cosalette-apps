---
status: Accepted
date: 2026-09-06
impact: high
tags: [configuration, architecture, mqtt, devices]
---

# ADR-003: TOML Inventory as the Configuration Boundary

## Status

Accepted **Date:** 2026-09-06

## Context

wiz2mqtt has to know which bulbs exist before it can register an entity, subscribe a push callback, or publish discovery. The legacy `wizcontrol.py` answered this with a hard-coded Python dict in the source. The rewrite needs a real configuration surface, and the question is how much that surface owns.

A WiZ bulb has two kinds of facts about it. **Inventory facts** — that it exists, its address, the name an operator wants on the MQTT topic — are known only to the operator and never change on their own. **Capability facts** — bulb class (RGB / TW / DW / SOCKET), the real Kelvin range, which scenes the firmware supports — are properties of the hardware that pywizlight reports at first contact via `get_bulbtype()`, and that a config file would only duplicate (and let drift).

cosalette gives the inventory a natural home: `Wiz2MqttSettings` with `extra="forbid"`, a `config_file`, and a `bulbs: list[BulbConfig]` field that the `name=_bulb_map` callable expands into one telemetry + one command registration per entry. The consumer-integration work (cap-10u.14) then raised a sharper version of the question: HA discovery metadata (`supported_color_modes`, `effect_list`, `min_kelvin`/`max_kelvin`) is per-bulb capability data — should the TOML own it so discovery can be capability-accurate offline, or does that pull hardware facts back into config?

### Deferred: per-bulb capability-filtered discovery metadata

PR-1 adopts **Option A** — a static wire-format superset in `models._HA_LIGHT_ENTITY` (`supported_color_modes: ["color_temp", "rgb"]`, the full 38-scene `effect_list`, a fixed 2200-6500 K range). Making the *advertised* discovery metadata per-bulb accurate is deferred to **cap-3tr** (child of epic cap-10u, blocked on cap-10u.14), which weighs two candidate mechanisms:

- **Mechanism B** — `app.discovery(enrich=...)` hook plus a Store-persisted capabilities cache. The adapter already builds `BulbCapabilities` at first contact; persist it in the cosalette `Store`, and have the `enrich` callback narrow `supported_color_modes` / `effect_list` / `min_kelvin` / `max_kelvin` per bulb from the cached record, falling back to the static superset before a bulb has ever been reached.
- **Mechanism C** — capabilities captured up front by the `discover` CLI subcommand (**cap-10u.15**) and written into `wiz2mqtt.toml` as optional per-bulb hints that the discovery generator reads. No runtime cache, deterministic offline generation, at the cost of a manual re-run when a bulb is swapped.

### Deferred: multi-bulb groups as config-owned, consumer-rendered

The legacy app exposed six write-only multi-bulb groups. The decision (`docs/planning/wiz2mqtt-group-entities-decision.md`, closing `cap-fux`) is that groups stay a consumer-side construct: their membership moves into `wiz2mqtt.toml` as `[[groups]]` (`{ name, members }`, `extra="forbid"` already admits the field), and wiz2mqtt's openHAB generator emits one openHAB Group Item per entry with member channel linkage — openHAB fans the command out and rolls state up natively. wiz2mqtt runs no group entity, publishes no `wiz2mqtt/<group>/state`, and subscribes no `wiz2mqtt/<group>/set`; HA MQTT discovery has no group primitive, so `app.discovery()` never emits groups. Implementation is deferred to **cap-0zt** (blocked on cap-10u.14, the openHAB generator it feeds).

## Decision

Make `wiz2mqtt.toml` the boundary for **inventory only**: each `[[bulbs]]` entry carries `name`, `ip`, an optional bare-hex `mac`, and an optional `when_unreachable` policy — nothing about what the bulb can do. Capabilities are auto-detected at runtime from pywizlight and are never declared in config. Consumers render from the app's live registry: `app.discovery()` publishes HA entities per configured bulb, and `cosalette schema openhab` generates the Generic MQTT Thing offline. Per-bulb capability-filtered discovery metadata is **deferred** (tracked as cap-3tr, mechanisms B and C above) — PR-1 advertises a static wire-format superset while runtime auto-detection still governs which commands the adapter forwards. Config-owned `[[groups]]` with consumer-rendered openHAB Group Items is **deferred** to cap-0zt.

```python
class BulbConfig(BaseModel):
    name: str                      # MQTT topic segment + entity identity
    ip: str                        # literal IPv4 — the transport handle (ADR-002)
    mac: str | None = None         # optional: verified once at startup
    when_unreachable: Literal["unavailable", "off"] = "unavailable"
    # no capability fields — bulb_class, kelvin range, scene list are runtime-detected

class Wiz2MqttSettings(cosalette.Settings):
    bulbs: list[BulbConfig] = []
    # groups: list[GroupConfig] = []   # deferred to cap-0zt
    model_config = SettingsConfigDict(env_prefix="WIZ2MQTT_", extra="forbid")
```

## Decision Drivers

- Inventory is operator knowledge that never changes on its own; capabilities are hardware facts pywizlight already reports — duplicating them in config only creates drift
- cosalette's `name=callable` expansion needs the inventory at registration time, so it has to be static configuration, not discovered
- `extra="forbid"` on the settings model makes adding one narrow field (the future `[[groups]]`, an optional capability hint) a one-line change with no schema ceremony
- Runtime auto-detection is the single source of truth for capabilities regardless of what discovery advertises, so a static discovery superset is safe — it can over-offer controls, never mis-route a command
- Keeping capability metadata and groups out of PR-1 keeps the consumer-integration change scoped and matches the cap-10u.6 gate's accepted worked example

## Considered Options

### Option 1: TOML owns inventory only, capabilities auto-detected (chosen)

`[[bulbs]]` carries name / ip / mac / when_unreachable. Bulb class, Kelvin range and scene support come from pywizlight at first contact. Discovery renders from the live registry with a static wire-format superset for now; capability-accurate discovery metadata is tracked as cap-3tr.

- *Advantages:* One source of truth per fact: operators own inventory, the bulb owns its capabilities; No capability drift between a config file and firmware; Adding a bulb is two lines; the `name=_bulb_map` callable does the rest; `extra="forbid"` keeps the surface small and rejects typos loudly
- *Disadvantages:* Offline `cosalette schema ha-discovery` cannot be capability-accurate without contacting hardware, so PR-1 over-advertises `supported_color_modes` / `effect_list` for TW and socket bulbs; HA shows an rgb picker / effect list on a bulb that lacks them until cap-3tr lands; A capability-accurate runtime path still needs somewhere to cache what was detected (mechanism B)

### Option 2: Fully declarative: capabilities also live in TOML

Each `[[bulbs]]` entry additionally declares `color_modes`, `kelvin_min`/`kelvin_max` and an `effects` list, and discovery + command validation read those instead of (or before) runtime detection.

- *Advantages:* Offline discovery generation is capability-accurate with no hardware and no cache; Deterministic: the file fully describes what HA and openHAB will show; A bulb that is offline at startup still gets correct discovery metadata
- *Disadvantages:* Duplicates facts pywizlight already knows, and the copy silently goes stale when firmware or hardware changes; Every operator now has to look up their bulb's class and Kelvin range to write a working config; Two sources of truth for 'can this bulb do rgb' — config and detection — need a precedence rule and a mismatch policy

### Option 3: Zero config: discover the whole inventory at startup

No inventory file at all. wiz2mqtt runs UDP broadcast discovery at startup, adopts every WiZ bulb it finds, and derives entity names from the bulb's MAC or module name.

- *Advantages:* Nothing to write — plug in a bulb and it appears; Inventory and capabilities are both always current
- *Disadvantages:* Entity identity (and therefore the MQTT topic and HA entity id) is no longer operator-controlled — it churns with whatever discovery returns; A bulb powered off at startup is simply absent, with no configured entity to mark unavailable; Depends on pywizlight's hang-prone broadcast discovery on the critical startup path and breaks on segmented networks; `name=callable` expansion has no static input, so the whole registration model would have to change

## Decision Matrix

| Criterion | TOML owns inventory only, capabilities auto-detected | Fully declarative: capabilities also live in TOML | Zero config: discover the whole inventory at startup |
| --- | --- | --- | --- |
| Single source of truth per fact (no drift) | 5 | 2 | 3 |
| Operator-controlled, stable entity identity | 5 | 5 | 1 |
| Offline discovery-generation accuracy | 2 | 5 | 2 |
| Minimal operator effort to add a bulb | 4 | 2 | 5 |
| Fit with cosalette `name=callable` registration | 5 | 5 | 1 |
| Robustness on a segmented / broadcast-restricted network | 5 | 5 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- `BulbConfig` stays four fields; adding a bulb is `name` + `ip`
- Capabilities have exactly one source — pywizlight at runtime — so nothing in config can go stale against firmware
- `app.discovery()` and `cosalette schema openhab` both render from the same inventory with no representative `.env.schema` profile needed
- `extra="forbid"` means the next narrow config addition (`[[groups]]` for cap-0zt, a capability hint for cap-3tr mechanism C) is a one-line field, not a schema negotiation

### Negative

- PR-1's HA `light` entity advertises a wire-format superset, so a TW or socket bulb shows controls it does not have until cap-3tr lands (mechanism B: `enrich` + Store-persisted capabilities cache; mechanism C: `discover` CLI subcommand cap-10u.15 writing per-bulb hints into `wiz2mqtt.toml`); command handling is unaffected because runtime detection still gates it
- Offline `cosalette schema ha-discovery` output is a superset, not a per-bulb-accurate document
- Multi-bulb groups are config-owned and consumer-rendered by decision but not yet implemented — `[[groups]]` + openHAB Group Item emission is deferred to cap-0zt (see `docs/planning/wiz2mqtt-group-entities-decision.md`)

_2026-09-06_
