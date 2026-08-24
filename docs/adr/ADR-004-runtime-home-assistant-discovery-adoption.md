---
status: Accepted
date: 2026-08-24
impact: moderate
tags: [mqtt, architecture, dependencies, lifecycle, testing]
---

# ADR-004: Runtime Home Assistant Discovery Adoption

## Status

Accepted **Date:** 2026-08-24

## Context

cosalette 0.6.2 shipped opt-in runtime HA discovery publication (upstream ADR-059, #385): when an app calls ``App.discovery()``, the framework builds payloads from its own live, post-expand registry via ``load_schema(app.asyncapi())`` — the identical loader/generator pipeline the ``cosalette schema ha-discovery`` CLI uses — and publishes them as retained QoS 1 messages on the first successful MQTT connect, clearing orphaned ``config`` topics for entities removed since the last run. Verified hands-on against the installed cosalette 0.6.3 source (``_wiring/_discovery.py``, ``_wiring/_infra.py``, ``testing/_discovery.py``).

All nine monorepo apps already pin ``cosalette>=0.6.3,<0.7``, so the feature is available everywhere with zero version work. Today every app instead relies on the offline flow: ``task <app>:schema:ha-discovery`` prints payloads that the operator hand-copies onto the broker. Four static-registry apps (airthings2mqtt, gas2mqtt, vito2mqtt, wallpanel-control) have enriched schemas producing real payloads guarded by hand-rolled state_topic cross-check integration tests (cap-5f8 pattern, reinvented per app). velux2mqtt achieves the same through the fragile two-step ``schema dump --resolve-settings`` + checked-in ``.env.schema`` profile (ADR-051). caldates2mqtt exits non-zero by design because 0.6.3 still skips array-item consumer annotations (no ``array_index`` opt-in upstream yet). jeelink2mqtt emits nothing until it gains ``consumer()`` annotations (cap-egy). suncast has no HA surface at all (SVG image payload). Two apps (wallpanel-control, suncast) pass ``store=None`` per the ADR-049 static-app convention, which disables the orphan-reconciliation half.

No app declares the ``cosalette[schema]`` extra that runtime discovery requires (PyYAML + jsonschema become runtime dependencies); CI's schema tasks pass today only because development dependencies happen to pull PyYAML into the shared workspace environment.

## Decision

Use ``App.discovery()`` runtime HA discovery publication for every app with a Home Assistant discovery surface, rolled out per app through dedicated adoption tasks, because it removes the operator hand-copy step, dissolves the ADR-051 phantom-entity class structurally, adds ghost-entity cleanup, and guarantees payload parity between what generates discovery and what publishes state.

Per-app verdicts:

| App | Verdict | Gating |
| --- | --- | --- |
| velux2mqtt | Adopt | none — first pilot; replaces the ``--resolve-settings`` two-step for discovery |
| airthings2mqtt, gas2mqtt, vito2mqtt, wallpanel-control | Adopt | none — lower urgency, offline flow already works |
| jeelink2mqtt | Adopt | blocked by cap-egy (needs ``consumer()`` annotations first) |
| caldates2mqtt | Adopt | blocked by cap-30z (array-item exposure undecided; generator still skips array items in 0.6.3, so adoption would emit zero payloads) |
| suncast | Excluded | no HA discovery surface (documented N/A) |
| wiz2mqtt | Out of scope here | governed by cap-10u.14 within the wiz2mqtt epic |

Adoption rules per task: bump the app to ``cosalette[schema]>=0.6.3,<0.7`` (the only way PyYAML/JSONSchema reach deployed environments, since app pyprojects are self-contained); call ``app.discovery()`` in the composition root; replace that app's hand-rolled state_topic cross-check test with ``cosalette.testing.assert_discovery_topics_published`` (see cap-6y0); update the README Home Assistant section to document that retained ``homeassistant/.../config`` topics now appear on broker connect. Once all adoptions land, the shared ``schema:ha-discovery`` task becomes deprecated for adopted apps; ``docs/schema.yaml``, ``schema:generate`` and the ``schema:check`` CI gate remain mandatory as drift-detection and openHAB-generation artifacts — openHAB has no runtime discovery protocol and stays on the offline CLI path permanently.

```python
# composition root (per adopting app)
app = cosalette.App(name="velux2mqtt", version="0.4.0")
app.discovery()  # retained HA configs published on first MQTT connect

# pyproject.toml
#   dependencies = ["cosalette[schema]>=0.6.3,<0.7", ...]

# integration test replaces the hand-rolled cross-check:
assert_discovery_topics_published(harness, payloads)
```

## Decision Drivers

- Eliminate the operator hand-copy step (and velux2mqtt's --resolve-settings dump dance) between generated discovery payloads and live broker state
- Dissolve the ADR-051 phantom-entity class structurally for HA discovery: runtime topics are constructed after callable name= specs resolve against real settings
- Gain ADR-048-style ghost-entity cleanup: removed config entries clear their retained discovery topics instead of lingering in Home Assistant
- Guarantee CLI/runtime parity by construction — both paths share load_schema() and HaDiscoveryGenerator, so they cannot silently diverge
- Consolidate five independently hand-rolled state_topic cross-check integration tests behind one framework helper

## Considered Options

### Option 1: Status quo — offline ha-discovery hand-copy flow

Keep generation entirely offline: each app's Taskfile runs ``cosalette schema ha-discovery docs/schema.yaml``, the operator copies payloads to the broker manually (velux2mqtt via ``schema dump --resolve-settings`` against a checked-in .env.schema profile).

- *Advantages:* Zero deployment-behaviour change: nothing appears on the broker unless the operator acts; No new runtime dependency — PyYAML stays a tooling-only concern; Operators review exactly what gets published before it lands on the broker
- *Disadvantages:* Every app change requires a manual re-publish step that is easy to forget, leaving stale discovery configs; Removed devices leave permanent ghost entities in Home Assistant; Five apps maintain near-identical hand-rolled cross-check integration tests against this exact divergence class; NameSpec apps depend on the operationally fragile .env.schema representative-profile trick

### Option 2: Adopt App.discovery() repo-wide (chosen)

Every app with an HA discovery surface opts in via one line in its composition root, rolled out through per-app adoption tasks; offline generation is deprecated for adopted apps while openHAB generation stays offline permanently.

- *Advantages:* One-line opt-in per app; discovery publishes itself correctly on every startup with zero operator steps; Phantom-entity failure mode cannot recur — payload topics derive from the post-expand registry; Orphaned discovery topics self-clear via reconcile_discovery_topics wherever a Store is configured; Hand-rolled cross-check tests collapse into the single assert_discovery_topics_published helper; Payload parity guaranteed: runtime path calls the same load_schema()/HaDiscoveryGenerator as the CLI
- *Disadvantages:* Each app gains a runtime dependency on cosalette[schema] (PyYAML + jsonschema); forgetting it fails closed — logged, swallowed, silent no-discovery; Deployment behaviour changes: retained homeassistant/.../config topics appear on broker connect whether or not the operator expects them; Republish happens on first connect per process lifetime only; out-of-band broker mutations do not self-heal until restart; Apps passing store=None (wallpanel-control) get publication but no orphan reconciliation unless they adopt a store

### Option 3: Runtime discovery for callable-NameSpec apps only

Adopt App.discovery() only where the offline pipeline is genuinely fragile (velux2mqtt now, jeelink2mqtt after cap-egy); the four static-registry apps keep the working offline flow indefinitely.

- *Advantages:* Targets the apps with actual correctness exposure (ADR-051 phantom class); Smallest blast radius: four apps see no deployment-behaviour change; Static apps keep operator-reviewed publishing
- *Disadvantages:* Two discovery mechanisms coexist indefinitely, so operators must know per app which flow applies; Static apps keep the manual republish step, ghost-entity accumulation, and duplicated cross-check tests; Divergence risk between the two regimes grows as apps evolve

## Decision Matrix

| Criterion | Status quo — offline ha-discovery hand-copy flow | Adopt App.discovery() repo-wide | Runtime discovery for callable-NameSpec apps only |
| --- | --- | --- | --- |
| Operator ergonomics (steps from code change to correct broker state) | 2 | 5 | 4 |
| Phantom-entity safety for settings-derived entity names | 2 | 5 | 5 |
| Ghost-entity hygiene on device removal | 1 | 5 | 3 |
| Deployment-behaviour risk (surprise retained topics, new runtime deps) | 5 | 3 | 4 |
| Test and maintenance burden across the monorepo | 2 | 5 | 4 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Discovery config reaches the broker automatically on first connect with zero operator steps for every adopting app
- The velux2mqtt-class phantom-entity failure cannot recur for HA discovery, by construction of the runtime registry
- Devices removed from config stop leaving permanent ghosts in Home Assistant wherever the app persists a Store snapshot
- Per-app hand-rolled state_topic cross-check integration tests can be replaced by the single assert_discovery_topics_published framework helper (cap-6y0)
- CLI and runtime discovery cannot drift: both consume load_schema() over the same AsyncAPI document

### Negative

- Every adopting app must switch to cosalette[schema]>=0.6.3,<0.7, making PyYAML and jsonschema runtime dependencies; a missed bump fails closed (logged and swallowed) and silently ships no discovery
- Retained homeassistant/.../config topics now appear on broker connect as a deployment-behaviour change; README updates are mandatory per adoption
- Discovery republishes only on the first successful connect per process lifetime — out-of-band broker mutations do not self-heal until restart
- wallpanel-control currently passes store=None (ADR-049 convention), so its adoption yields publication without orphan reconciliation unless it also adopts a store
- openHAB keeps its capability asymmetry: no runtime protocol exists, so docs/schema.yaml, schema:generate and the schema:check CI gate stay mandatory for every app regardless of HA adoption

_2026-08-24_
