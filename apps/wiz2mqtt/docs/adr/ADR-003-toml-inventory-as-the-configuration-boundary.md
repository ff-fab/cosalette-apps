---
status: Accepted
date: 2026-09-06
impact: high
tags: [configuration, architecture, mqtt, devices]
---

# ADR-003: TOML Inventory as the Configuration Boundary

## Status

Accepted **Date:** 2026-09-06 | Amended **Date:** 2026-09-07 | Amended **Date:** 2026-09-08 | Amended **Date:** 2026-09-13 | Amended **Date:** 2026-09-15

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
    mac: str | None = None         # optional: verified at first successful contact
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

## Amendment (2026-09-07) — Additive

**Rationale:** cap-3tr is resolved. ADR-003 deferred per-bulb capability-filtered HA discovery metadata to a later choice between Mechanism B (runtime enrich + Store cache) and Mechanism C (discover CLI writing TOML capability hints). Mechanism B is chosen and implemented, because it makes runtime discovery per-bulb accurate while preserving ADR-003's central invariant that capabilities are never declared in config.

### Additional Sub-Decision: Resolved: per-bulb capability-filtered discovery via Mechanism B

Use **Mechanism B** — `app.discovery(enrich=...)` plus a `DeviceStore`-persisted capabilities cache — to make the advertised Home Assistant `light` metadata per-bulb accurate.

The `bulb_entity` telemetry handler receives a per-bulb `DeviceStore` (keyed by the bulb name) and writes the auto-detected `BulbCapabilities` into it, only when they change. The `app.discovery(enrich=...)` hook (see `wiz2mqtt/discovery.py`) reads that cache back at publish time via `app.store.load(<bulb name>)` and narrows the emitted config in place: `supported_color_modes` drops `rgb`/`color_temp` the bulb lacks (falling back to `brightness` or `onoff`), the Kelvin range tracks the detected `KelvinRange`, and `effect`/`effect_list` are removed when the firmware has no effects.

The cache holds *derived* data that every bulb contact refreshes, so ADR-003's no-capabilities-in-config invariant is intact — nothing in `wiz2mqtt.toml` describes what a bulb can do, and there is nothing to drift.

**Mechanism C was rejected:** writing capability hints into `wiz2mqtt.toml` reintroduces exactly the config/firmware drift ADR-003's Option 2 ("Fully declarative") scored lowest on, and needs a precedence rule against runtime detection.

**Convergence timing (accepted).** `app.discovery()` publishes retained config once, on first MQTT connect, before any bulb has been contacted — so the cache is empty on a bulb's very first run and the static superset in `models._HA_LIGHT_ENTITY` is advertised. Capabilities are detected as the bulb is reached, persisted on shutdown, and the *next* start publishes the narrowed metadata. A retyped (physically swapped) bulb converges the same way: the run after the swap detects the new class and the following start advertises it. This one-restart lag is inherent to publish-on-connect and was accepted as the cost of keeping capabilities out of config.

**Offline path unchanged.** `cosalette schema ha-discovery` does not run the enrich hook and keeps emitting the documented static superset — offline generation stays hardware-free and is not per-bulb accurate, as ADR-003 already accepted.

### Additional Positive Consequences

- Home Assistant no longer shows an RGB picker, effect list, or full Kelvin slider on a tunable-white, dimmable-white, or socket bulb once wiz2mqtt has contacted it and been restarted — the advertised light matches the hardware.
- The capability cache is refreshed from the bulb on every contact, so it cannot drift from firmware; config remains inventory-only (ADR-003 invariant preserved).

### Additional Negative Consequences

- Discovery is per-bulb accurate only from the second run onward: a freshly onboarded or retyped bulb advertises the static superset until wiz2mqtt has reached it once and been restarted (accepted; documented in the Getting Started guide).
- A hard kill before a graceful shutdown loses that run's freshly detected capabilities, deferring convergence by one more restart, because the DeviceStore is flushed on shutdown.

## Amendment (2026-09-08) — Minor

!!! note "Editorial note (2026-09-08)"
    cap-0zt implements the previously deferred group inventory: optional [[groups]] entries contain a unique name and a non-empty list of distinct, declared bulb names. Names cannot collide with bulbs or other groups. Runtime registrations and HA discovery continue to use only settings.bulbs.

!!! note "Editorial note (2026-09-08)"
    The deployment command wiz2mqtt-openhab (task wiz2mqtt:openhab) resolves the real TOML inventory through cosalette's public schema CLI, then adds one plain openHAB Group per configured group to the generated Items. Each member's Color command Item retains its existing channel link and joins the group; openHAB handles command fan-out. Plain groups intentionally do not select a state aggregation policy. Individual telemetry Items retain state display. The existing schema:openhab task remains a sample-schema renderer.

!!! note "Editorial note (2026-09-08)"
    The generator rejects bulb and group names that collide after openHAB identifier normalization and fails if a member's expected Color command Item is absent. It creates no group MQTT topics. This implementation supersedes the earlier statements that group support is deferred or blocked on cap-10u.14.

## Amendment (2026-09-13) — Additive

**Rationale:** ADR-007 (mains power awareness through power sources) and ADR-008 (desired state with restore on return to reachability) extend the inventory. A circuit is operator knowledge in the same way a bulb address is, so the `[[power_sources]]` block belongs in `wiz2mqtt.toml`. This amendment records the new keys and the legacy mapping. The invariant of ADR-003 holds: nothing in the file describes what a bulb can do.

### Additional Sub-Decision: The `[[power_sources]]` block

The inventory gains an optional `[[power_sources]]` list. Each entry declares a circuit: a unique `name`, exactly one of `group` (a declared group name) or `members` (a non-empty list of declared bulb names), an optional `signal_topic`, `when_unreachable` (`"fault"` by default, or `"no_power"`), `enable_power_on_request` and `enable_power_off_request` (both `false` by default), `power_off_idle_delay` (a bare float in seconds) and `wiz_bulbs_only` (`false` by default). The validator follows the pattern of `_groups_valid`. `signal_topic` rejects `+`, `#` and an empty value.

The per-bulb keys `power_source` (an optional power source name) and `restore_previous_state` (`false` by default) join `[[bulbs]]`. The top-level key `queued_command_ttl` (a bare float in seconds, default `86400.0`) joins the settings.

```toml
queued_command_ttl = 86400.0

[[bulbs]]
name = "living-room"
ip = "192.168.1.102"
power_source = "downstairs-circuit"
restore_previous_state = true

[[power_sources]]
name = "downstairs-circuit"
group = "downstairs"
signal_topic = "openhab/relay/downstairs/state"
when_unreachable = "fault"
```

### Additional Sub-Decision: Membership resolution order

The membership of a bulb resolves in this order:

1. The `power_source` key on the bulb wins.
2. A power source block that names the group of the bulb claims the bulb.
3. The bulb is not power-aware. The bulb behaves as it does today.

A bulb belongs to a maximum of one power source.

### Additional Sub-Decision: Legacy mapping of `when_unreachable`

`when_unreachable` moves from the bulb to the power source. `extra="forbid"` makes a stale bulb-level key a hard `ValidationError` at startup, and the repository has no deprecation precedent and no aliases. The migration maps a legacy bulb-level `when_unreachable = "off"` to an implicit single-bulb power source with `when_unreachable = "no_power"`, and emits a warning that names the replacement.

### Additional Positive Consequences

- A circuit is declared once, and its bulbs follow through the group reference; the per-bulb `power_source` key handles the exception.
- The ADR-003 invariant holds: every new key is operator knowledge, and none is a hardware fact.

### Additional Negative Consequences

- `BulbConfig` grows from four fields to six, and the settings model gains a second list block and a top-level duration.
- An operator who set `when_unreachable` on a bulb sees a warning at the first start after the upgrade and must move the key.

## Amendment (2026-09-14) — Corrective

Before Pydantic validation, compatibility normalization maps legacy bulb-level `when_unreachable = "off"` to an implicit single-member source with `when_unreachable = "no_power"`, removes the legacy key, and logs its named replacement. Every other legacy value is rejected with a migration error. Validation therefore never sees an unsupported legacy field. `BulbConfig` grows from four to five fields, not six; tests cover the accepted legacy value, rejected values, and no legacy key.

## Amendment (2026-09-15) — Corrective

**Rationale:** ADR-003 used first-contact and startup wording that is incompatible with the adapter's lazy, retryable initialization and the MAC verification boundary recorded in ADR-002. Capability-derived discovery metadata must only be cached from an accepted initialization attempt.

> **Justification for amendment (not supersession):** Supersession is not warranted because the implemented decision that TOML owns inventory and runtime owns capabilities remains unchanged. The correction only clarifies when existing runtime detection becomes eligible for persistence and discovery enrichment, with no schema or migration change.

### Revised Decision

Make `wiz2mqtt.toml` the boundary for inventory only: each `[[bulbs]]` entry carries operator-owned identity and power-source configuration, never hardware capabilities. Runtime initialization detects capabilities from pywizlight on demand. When optional MAC verification is configured, capability data becomes eligible for adapter caching, capability persistence, and discovery enrichment only after the same initialization attempt accepts the reported MAC (or logs an absent MAC as unverifiable). A failed capability or MAC-read attempt is not cached and does not establish discovery metadata; a later first-contact attempt retries the complete sequence. Startup registers the configured inventory without contacting bulbs, and retained discovery uses only capability records that were successfully persisted before the discovery publication.

!!! note "Editorial note (2026-09-15)"
    The historical "at startup", "first contact", and "next start" timing statements are superseded where they imply one non-retryable probe or that capability detection alone establishes a durable record. Contact is lazy and retryable; only an accepted, persisted attempt can narrow later discovery metadata.

!!! note "Editorial note (2026-09-15)"
    This clarification does not change the accepted offline path: hardware-free schema generation continues to emit the documented static superset.

### Additional Positive Consequences

- Discovery enrichment never reflects capability data from a connection that failed identity verification.

### Additional Negative Consequences

- A newly configured bulb with repeated failed initialization continues to advertise the static discovery superset until an accepted attempt persists its capabilities.
