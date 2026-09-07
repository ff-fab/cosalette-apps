# Decision: per-bulb capability-filtered HA discovery metadata

- **Status:** PROPOSED — awaiting decision owner
- **Bead:** `cap-3tr` (feature; child of epic `cap-10u`, unblocked by closed `cap-10u.14`)
- **Seeds:** ADR-003 "Deferred: per-bulb capability-filtered discovery metadata"
- **Recommendation:** Mechanism B (runtime `enrich` + `Store` cache); keep the
  offline superset as-is

## The question

Today wiz2mqtt advertises a **static wire-format superset** in
[`models._HA_LIGHT_ENTITY`](../../apps/wiz2mqtt/packages/src/wiz2mqtt/models.py):

```python
"supported_color_modes": ["color_temp", "rgb"],
"effect": True,
"effect_list": list(WIZ_EFFECT_LIST),   # all 38 scenes
"min_kelvin": 2200, "max_kelvin": 6500,
```

Every configured bulb gets the same block, so Home Assistant shows an RGB picker,
the full effect list, and a 2200–6500 K slider even on a tunable-white or socket
bulb that lacks them. Command handling is already correct — runtime
`BulbCapabilities` detection (pywizlight `get_bulbtype()` at first contact) gates
what the adapter forwards — but the **advertised** discovery metadata is not
per-bulb accurate. cap-3tr closes that gap.

## Constraints inherited from prior decisions

- **ADR-002 (IP is identity):** the `discover` CLI is an onboarding aid,
  explicitly *not* wired into daemon addressing.
- **ADR-003 (TOML = inventory boundary):** capabilities are hardware facts
  pywizlight reports at runtime and are **never declared in config** — duplicating
  them in TOML "only creates drift" (its central decision driver). `extra="forbid"`
  on `Wiz2MqttSettings` means a new optional field is a one-line change.
- ADR-003 already accepts that the **offline** `cosalette schema ha-discovery`
  output is "a superset, not a per-bulb-accurate document."

## Framework facts (verified against cosalette 0.9.1)

- **`app.discovery(enrich=...)` exists.** The `enrich(channel, prop, config)`
  callback fires once per emitted entity, immediately before its payload is built,
  and may mutate `config` in place — including keys the curated surface doesn't
  reach. This is purpose-built for narrowing `supported_color_modes` / `effect_list`
  / `min_kelvin` / `max_kelvin` per bulb.
- **A `Store` is configured by default** (zero-config `JsonFileStore` under
  `$XDG_STATE_HOME/wiz2mqtt/store.json`), and handlers can take a per-entity
  `DeviceStore`. The adapter already builds `BulbCapabilities` at first contact, so
  persisting it is a small addition.
- **Retained discovery is published once, on first successful MQTT connect.** This
  is the key timing constraint for Mechanism B (see below).

## Option B: runtime `enrich` + `Store`-persisted capability cache (recommended)

**What:** The adapter writes each bulb's detected `BulbCapabilities` into the
`Store` at first contact. `app.discovery(enrich=_narrow)` reads the cached record
per bulb and narrows the entity `config`; if a bulb has never been reached, it
leaves the static superset.

**Why this approach:**

- Keeps ADR-003's core invariant intact — **capabilities stay a runtime fact**.
  The Store holds *derived, self-refreshing* data (re-detected on every contact),
  not authoritative config, so there is no drift: swap a bulb and the next contact
  overwrites the cache.
- Uses the framework's designated escape hatch (`enrich`) for exactly its intended
  purpose; no new config surface, no new CLI output, no generator changes.
- Zero operator effort — accuracy emerges automatically.

**Trade-offs:**

- **First-run timing.** Discovery is published once per process start, and on a
  fresh install the cache is empty at that moment (bulbs are contacted *after*
  discovery publishes). So run 1 advertises the superset; capabilities are cached
  as bulbs connect; **run 2 (after the next restart) publishes the narrowed
  metadata**, and it stays accurate thereafter (JsonFileStore persists). This is
  precisely the "fall back to the superset before a bulb has been reached" that
  ADR-003 anticipated — it is self-healing, but not first-boot-accurate.
- Mid-run republish (narrowing the instant a capability is first detected) would
  need a framework hook to re-emit discovery on demand, which is not currently
  exposed. Out of scope; the restart-convergence behaviour is acceptable for a
  stable home inventory.

**Tooling note:** testable with `AppHarness.create(store=MemoryStore())` — seed the
cache, assert the `enrich` callback narrows each entity; no disk I/O, no hardware.

## Option C: `discover` CLI writes per-bulb capability hints into `wiz2mqtt.toml`

**What:** Extend the just-merged `discover` CLI (`cap-10u.15`) to also fetch
`get_bulbtype()` per bulb and emit optional capability hints into the `[[bulbs]]`
blocks. `BulbConfig` grows optional capability fields; the discovery generator in
`models.py` reads them to narrow the advertised metadata.

**Why this approach:**

- **Deterministic and offline-accurate:** `cosalette schema ha-discovery` can
  produce per-bulb-correct output with no hardware and no cache, because the facts
  live in the file.
- Correct on the very first boot (no restart-convergence gap).

**Trade-offs:**

- **Directly reopens the ADR-003 drift question it decided against.** Capability
  hints in TOML are the "fully declarative" Option 2 that ADR-003 scored lowest on
  single-source-of-truth: the hints go stale the moment firmware changes or a bulb
  is swapped, and there is no forcing function to re-run the CLI.
- Needs a precedence/mismatch rule between the TOML hint and runtime detection
  (which one wins when they disagree?).
- Larger surface: CLI capability fetch, `BulbConfig` fields + validation, generator
  wiring — for the offline path that ADR-003 already accepts as a superset.

## Option D: hybrid — C for offline schema, B for runtime discovery

Use the TOML hints (C) only for the offline `cosalette schema ha-discovery`
generator, and the `enrich`+cache (B) for runtime `app.discovery()`.

- *Advantages:* both paths per-bulb accurate, including first boot and offline docs.
- *Disadvantages:* the union of both mechanisms' surface and both failure modes
  (stale hints *and* restart convergence), plus two code paths advertising
  potentially different metadata. Only worth it if offline per-bulb accuracy becomes
  a hard requirement — which ADR-003 explicitly says it is not today.

## Recommendation

**Adopt Mechanism B and leave the offline generator emitting the superset.**

Home Assistant consumes the *runtime* `app.discovery()` payload, and B makes that
per-bulb accurate while preserving ADR-003's "no capabilities in config" invariant
with the least new surface. The only real cost — superset on the first boot before
any bulb has been contacted — is bounded, self-healing after one restart, and
already sanctioned by ADR-003. Revisit C or the hybrid only if first-boot or
offline per-bulb accuracy becomes a firm requirement.

If accepted, this decision amends ADR-003's deferred section and is recorded as a
new ADR (via the `adr-create` skill).

## Proposed implementation sketch (Mechanism B, pending approval)

1. Persist `BulbCapabilities` per bulb from the adapter at first contact
   (`DeviceStore` keyed by bulb name, JSON-serialised).
2. Add `_narrow_discovery(channel, prop, config)` in `models.py` (or a new
   `discovery.py` helper) that, given a bulb's cached capabilities, deletes/edits
   `supported_color_modes`, `effect`/`effect_list`, `min_kelvin`/`max_kelvin`.
3. Wire `app.discovery(enrich=_narrow_discovery)` in `main.py`, resolving the bulb
   name from the channel to look up its cached record; no cache entry ⇒ leave the
   superset.
4. Unit tests with `MemoryStore`: superset when cache empty; RGB bulb keeps rgb; TW
   bulb loses rgb + effects; kelvin range narrowed to the detected range.
5. Amend ADR-003 / create the follow-up ADR.

## Open questions for the decision owner

1. **Mechanism:** B (recommended), C, or the D hybrid?
2. Is **first-boot** superset-then-converge acceptable, or is first-boot per-bulb
   accuracy a hard requirement (which would push toward C/D)?
3. Should the offline `cosalette schema ha-discovery` output stay a documented
   superset, or must it become per-bulb accurate too?
