# cosalette Framework Enhancement: Emit channel-level `x-cosalette-app` during schema generation

**Date:** 2026-07-23
**Author:** ha-discovery / schema-enrichment maintainer (cap-3bz)
**Status:** Implemented in cosalette 0.5.7 — `schema init` / `schema generate` now
auto-emit channel-level `x-cosalette-app` from the App registry, so the tag no longer
needs hand-adding or re-adding after regeneration. The body below describes the
pre-0.5.7 problem that motivated the ask.
**Context:** Surfaced during cap-3bz HA discovery schema enrichment, where every app's
`schema.yaml` was enriched with consumer metadata. `cosalette schema ha-discovery`
resolves the owning app via `channel.app_name or "unknown"`, which reads the
channel-level `x-cosalette-app` tag — but `cosalette schema init` / `schema generate`
never emit that tag, so it must be hand-added and re-added after every regeneration.
**Related beads:** sibling of `cap-075` and `cap-nx5` (both framework gaps surfaced by
cap-3bz).

---

## Executive Summary

`cosalette schema ha-discovery` depends on a channel-level `x-cosalette-app: <app_name>`
tag to resolve which app owns a channel (code path: `channel.app_name or "unknown"`).
Schema generation (`schema init` / `schema generate`) does **not** emit this tag. As a
result, every app in this monorepo hand-adds `x-cosalette-app` to each channel in its
committed `schema.yaml`, and must **re-add it by hand after every schema
regeneration**, because regeneration strips any field it does not itself produce.

**This proposal asks the framework to auto-emit `x-cosalette-app: <app_name>` on each
channel during schema generation, derived from the same App registry that
`cosalette manifest` already uses, so the tag survives regeneration like every other
generated field.**

---

## Problem Statement

### ha-discovery needs the tag; generation does not produce it

`cosalette schema ha-discovery` reads `channel.app_name` (falling back to `"unknown"`)
to attribute each channel to its owning app when building Home Assistant discovery
payloads. That value comes from the channel's `x-cosalette-app` extension tag.

`cosalette schema init` and `schema generate` introspect the app's declared handlers
and emit channels, payload schemas, and other `x-cosalette-*` extensions — but they
never emit `x-cosalette-app`. The one piece of metadata ha-discovery needs to resolve
the app name is precisely the piece generation omits.

### The tag is hand-maintained and stripped on every regen

Because generation does not produce it, each app carries a hand-added
`x-cosalette-app: <name>` line on each channel. Regeneration rewrites the channel block
from introspection and drops the hand-added tag, so it must be re-added by hand every
time the schema is regenerated.

**Evidence:**

- A fresh regeneration of `vito2mqtt` produces **0** occurrences of `x-cosalette-app`,
  though its committed `schema.yaml` carries **6** (one per channel).
- During the cap-nx5 migration, regenerating `velux2mqtt` **stripped** its
  `x-cosalette-app` tag, which then had to be re-added by hand.

This is a silent regression trap: a routine `schema generate` (e.g. after adding a
telemetry field) quietly removes the app attribution, and ha-discovery falls back to
`"unknown"` until someone notices and re-adds the tag.

### Scope of the problem

All eight apps are affected — every `schema.yaml` with enriched channels carries a
hand-added `x-cosalette-app` tag today:

| App | `x-cosalette-app` occurrences in committed `schema.yaml` |
|-----|--------------------------------------------------------|
| vito2mqtt | 6 |
| gas2mqtt | 2 |
| airthings2mqtt | 1 |
| velux2mqtt | 1 |
| wallpanel-control | 1 |
| caldates2mqtt | 0 (no consumer-enriched channels yet) |
| suncast | 0 |
| jeelink2mqtt | 0 (dynamic per-sensor stream topics) |

Every occurrence above is hand-maintained and at risk of being stripped by the next
regeneration.

---

## Proposed Solution

### Auto-emit `x-cosalette-app` from the App registry during generation

`cosalette schema init` / `schema generate` should emit `x-cosalette-app: <app_name>`
on **each generated channel**, derived from the App registry — the same source of truth
`cosalette manifest` already consults for the app name. Because the tag is then produced
by generation itself, it survives regeneration exactly like the payload schema,
`x-cosalette-consumer`, and every other generated field.

```yaml
# Generated automatically for each channel (illustrative):
channels:
  vito2mqtt/outdoor/state:
    x-cosalette-app: vito2mqtt        # ← emitted by generation, not hand-added
    x-cosalette-consumer:
      device_class: temperature
      unit_of_measurement: "°C"
    # ... payload schema ...
```

The app name is already unambiguous at generation time: the generator is invoked
against a specific `App(...)` instance whose `name=` is the value `cosalette manifest`
prints. No new input or configuration is required — the generator already holds the
value it needs.

### Result: zero hand-maintenance, no regen drift

- App authors stop hand-adding `x-cosalette-app` to channels.
- `schema generate` becomes idempotent with respect to app attribution — running it
  never removes the tag.
- ha-discovery reliably resolves `channel.app_name` instead of falling back to
  `"unknown"`.

---

## Secondary Observation (follow-up opportunity, not the core ask)

While the core ask is about `x-cosalette-app`, the same class of "hand-applied after
generation, stripped on regen" problem partially has a **known, working solution** for
a *different* tag — worth documenting as a migration opportunity for existing apps.

`x-cosalette-consumer` attached via
`pydantic.Field(json_schema_extra={...})` on a **`state_model`** field **does** survive
regeneration, because generation introspects the model and re-emits the extra. After
the cap-nx5 migration, `velux2mqtt` relies on exactly this: its consumer metadata lives
on the model, so regeneration reproduces it.

By contrast, `vito2mqtt` and `gas2mqtt` still hand-apply `x-cosalette-consumer` to the
generated schema *after* generation, which means (like `x-cosalette-app` today) it must
be re-applied on every regen.

**Follow-up opportunity:** migrate the remaining apps to the model-driven
`json_schema_extra` pattern for `x-cosalette-consumer`, eliminating that post-generation
hand-maintenance. This is orthogonal to the `x-cosalette-app` ask — `x-cosalette-app` is
a *channel*-level, app-identity tag that has no natural home on a payload field model,
which is exactly why the framework (not the app) should emit it during generation.

---

## Impact on Existing Apps

| App | Today | After this change |
|-----|-------|-------------------|
| vito2mqtt | 6 hand-added tags, stripped on regen | Tags emitted by generation; hand-added lines removable |
| gas2mqtt | 2 hand-added tags | Emitted automatically |
| airthings2mqtt | 1 hand-added tag | Emitted automatically |
| velux2mqtt | 1 hand-added tag (re-added after cap-nx5 regen) | Emitted automatically |
| wallpanel-control | 1 hand-added tag | Emitted automatically |
| caldates2mqtt / suncast | no enriched channels yet | Tag present as soon as channels are generated |
| jeelink2mqtt | dynamic stream topics | Tag emitted for statically-declared channels |

After this lands, each app can delete its hand-added `x-cosalette-app` lines in a
follow-up cleanup; the framework then owns the tag.

---

## What This Does NOT Change

- **`x-cosalette-consumer` semantics** — unchanged; this proposal only adds
  `x-cosalette-app` emission (the secondary observation is advisory, not part of the
  ask).
- **ha-discovery logic** — unchanged; it keeps reading `channel.app_name`. This proposal
  only ensures that value is populated by generation.
- **Channel/payload schema shape** — unchanged apart from the added `x-cosalette-app`
  key per channel.
- **App-side handler declarations** — unchanged; the app name is already known to the
  generator via the `App(...)` instance.

---

## Alternatives Considered

1. **Keep hand-adding the tag (status quo).** Rejected: it is stripped on every regen,
   is a silent regression trap, and scales linearly with the number of channels across
   eight apps.

2. **Move `x-cosalette-app` onto a payload field via `json_schema_extra`** (mirroring the
   `x-cosalette-consumer` survival pattern). Rejected: `x-cosalette-app` is a
   channel-level identity tag, not a payload-property concern; there is no natural field
   to hang it on (channels with `type: object` or no `state_model` have no field at
   all), and it would duplicate the app name across every field of every channel.

3. **Post-process the schema in a repo-level script after generation.** Rejected: it
   re-introduces a separate maintenance step, must be kept in sync across apps, and does
   not help downstream consumers who regenerate schemas outside this repo. The App
   registry already holds the name at generation time — the framework is the correct
   owner.

---

## Summary

ha-discovery resolves channel ownership via `channel.app_name`, but schema generation
never emits the `x-cosalette-app` tag that populates it. Apps hand-add the tag and must
re-add it after every regeneration. This proposal makes generation emit
`x-cosalette-app: <app_name>` per channel from the App registry, so app attribution
survives regeneration by construction — eliminating hand-maintenance across all eight
apps and closing a silent regression trap. A follow-up opportunity is noted to migrate
remaining apps' `x-cosalette-consumer` tags to the model-driven `json_schema_extra`
pattern that already survives regeneration.
