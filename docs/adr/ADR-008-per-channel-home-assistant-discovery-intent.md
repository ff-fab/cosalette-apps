---
status: Accepted
date: 2026-09-10
impact: high
tags: [architecture, mqtt, telemetry, devices, documentation]
---

# ADR-008: Per-Channel Home Assistant Discovery Intent

## Status

Accepted **Date:** 2026-09-10

## Context

cosalette 0.9.4 (upstream ADR-073) changed the `schema ha-discovery` / `schema openhab` gate from registry-wide to per-channel. Before, one annotated channel covered for every un-annotated sibling and the command exited 0. Now every consumer-visible channel that emits no discovery entity is reported by name and the command exits 1.

That is a better contract, but it turned an implicit repo-wide convention into a decision every app must state out loud. Across nine apps, 18 channels emit nothing: `/set` command channels, command acknowledgement payloads, a diagnostic Optolink feed, a long-running disinfection device, a magnetometer debug feed, and a channel whose payload is a rendered SVG rather than a datapoint. Each needs an explicit answer, and the answers are not interchangeable.

The upgrade also exposed a trap that cost this repo a silent regression. `discoverable=` is reconciled per channel, and a command's outbound `/state` channel merges into a same-named telemetry channel with the opt-out winning on merge. Registering a *returning* command `discoverable=False` therefore also hides the telemetry sensors published under that name. vito2mqtt lost 10 Home Assistant sensors and 4 HA devices this way, taking `ha-discovery` from 22 payloads to 12, and neither `cosalette schema check` nor any test caught it: the CI gate compares registered device names and never reads `x-cosalette-discoverable`.

This ADR is recorded at monorepo scope for the same reason ADR-004 and ADR-005 were: the rule binds every app, and per-app ADRs would drift.

## Decision

Every channel that emits no discovery entity must state why, and the choice between the two available mechanisms is determined by whether the channel's registration also publishes state.

**Rule 1 — a channel that is genuinely not a consumer entity declares `discoverable=False`.** Diagnostic feeds, debug telemetry, command acknowledgements and payloads that are not datapoints. The declaration carries a comment naming the reason.

**Rule 2 — before opting a command out, make its handler void.** Annotate it `-> None` and set no `state_model=`. A void command emits no `/state` channel, so nothing merges and the opt-out stays confined to `/set`. If the handler must publish state, Rule 1 is unavailable: opting out would take the telemetry sensors with it.

**Rule 3 — a command that must publish state annotates its payload model with `consumer()` instead.** The `/set` channel then emits real Home Assistant controls. This is strictly better than hiding it: the app gains control surface it did not have.

**Rule 4 — a payload whose only property is an array of objects uses a channel-level `ha_entities()` composite,** not per-property `consumer()` annotations. An array item has no single value, so per-property annotations are inert. The composite derives one entity from the whole payload.

**Rule 5 — every declaration is locked by a test.** Each affected app carries a `TestDiscoveryOptOut` golden set asserting the exact opted-out channel set against the committed `docs/schema.yaml`. Neither a stripped flag nor a leaked one is detectable any other way.

```python
# Rule 2 — void the handler, then the opt-out is safe.
async def handler(payload: str, port: OptolinkPort) -> None:
    ...
    return None

for group in COMMAND_GROUPS:
    app.add_command(
        name=group,
        # A /set channel is not an HA entity; the sensors come from the
        # telemetry half. Safe ONLY because the handler is void.
        discoverable=False,
        func=make_command_handler(group),
    )

# Rule 3 — the handler must publish state, so annotate /set instead.
class DisplayCommand(BaseModel):
    state: Annotated[
        Literal["on", "off"] | None,
        Field(default=None, json_schema_extra=consumer(display_name="Display Power")),
    ] = None

# Rule 4 — array of objects needs a channel-level composite.
_EVENT_COUNT_SENSOR = ha_entities(
    ha_entity(
        component="sensor",
        name="Events",
        extra={"value_template": "{{ value_json.events | length }}"},
    )
)
```

## Decision Drivers

- A silent loss of Home Assistant entities is the worst failure mode here: the app keeps running, MQTT keeps publishing, and only the user's dashboard goes quiet.
- The per-channel gate is not optional. An app that answers it wrongly fails CI or ships wrong; there is no third state.
- `cosalette schema check` never reads `x-cosalette-discoverable`, so intent that is not asserted by a test is not enforced at all.
- The two mechanisms look interchangeable at the call site and are not. The difference depends on whether the handler returns a value, which is invisible from the registration.
- Nine apps and eighteen channels is past the point where a convention survives in commit messages.

## Considered Options

### Option 1: Per-channel intent with a mechanism rule keyed on handler voidness (chosen)

Declare `discoverable=False` on channels that are genuinely not entities, but only after confirming the handler publishes no state; annotate the payload model with `consumer()` when it does. Lock every declaration with a golden-set test.

- *Advantages:* Keeps every existing Home Assistant entity while satisfying the per-channel gate.; The failure mode that bit vito2mqtt becomes impossible to reintroduce silently: the golden-set test fails.; wallpanel-control gains a select and a number, so the display is controllable from Home Assistant for the first time.; The rule is mechanical. An author can apply it without understanding the channel-merge internals.
- *Disadvantages:* Requires a test per affected app, which is real maintenance.; Rule 3 adds entities rather than hiding a channel, so a `/set` channel becomes visible where an author might have preferred silence.; The voidness rule depends on cosalette internals that could change in a future release.

### Option 2: Blanket `discoverable=False` on every non-emitting channel

Apply the flag wherever the gate complains, without distinguishing void from returning handlers.

- *Advantages:* Smallest diff and the most obvious reading of the upstream guidance.; One rule, no conditionals, nothing to explain.
- *Disadvantages:* This is exactly what deleted vito2mqtt's 10 sensors and 4 devices. It is the option that produced the defect.; The loss is silent: the gate passes, CI is green, and the entities are simply gone.; Leaves wallpanel-control unfixable, because opting out `displayCommand` also hides `displayState`.

### Option 3: Pin cosalette back to 0.9.3 for the affected apps

Leave the two apps that trip the gate on the previous release and upgrade them once cosalette offers per-half control.

- *Advantages:* Defers the problem without touching app design.; Superficially the smallest risk.
- *Disadvantages:* Does not work. This is a single-lock uv workspace: uv resolves one cosalette version for every member, so an app-level specifier of `>=0.9.3` still installs 0.9.4 while any sibling requires it.; Would have to downgrade all ten pins, abandoning the upgrade entirely.; Leaves the underlying trap undocumented and unguarded for the next release.

### Option 4: Wait for upstream per-half control

Ask cosalette for a `state_discoverable=` or equivalent that separates a registration's `/set` and `/state` channels, and hold the upgrade until it lands.

- *Advantages:* Would give the cleanest expression of the intent, with no dependency on handler voidness.; Fixes the root cause rather than working around it.
- *Disadvantages:* Blocks nine apps on an unscheduled upstream change.; The void-handler route already achieves the same outcome today and is arguably more honest: a command that publishes nothing should not declare a state channel.; Does not address rules 4 and 5, which are needed regardless.

## Decision Matrix

| Criterion | Per-channel intent with a mechanism rule keyed on handler voidness | Blanket `discoverable=False` on every non-emitting channel | Pin cosalette back to 0.9.3 for the affected apps | Wait for upstream per-half control |
| --- | --- | --- | --- | --- |
| Preserves existing Home Assistant entities | 5 | 1 | 3 | 5 |
| Detects a future regression | 5 | 1 | 1 | 2 |
| Works with the current toolchain | 5 | 5 | 1 | 1 |
| Cost to apply to a new app | 3 | 5 | 4 | 4 |
| Unblocks the 0.9.4 upgrade now | 5 | 4 | 1 | 1 |
| Honesty of the resulting schema | 5 | 2 | 2 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Every one of the 22 vito2mqtt discovery payloads is restored, and a golden-set test fails if any is lost again.
- wallpanel-control's display is controllable from Home Assistant for the first time, via a select and a number on the `/set` channel.
- suncast gains a discovery suite where it previously had none; its single channel now emits nothing by declaration rather than by accident.
- caldates2mqtt emits one event-count sensor per calendar, up from zero, through the channel-level composite.
- The trap is written down in `.github/instructions/cosalette.instructions.md`, so every agent that opens a Python file in this repo reads it before touching a registration.

### Negative

- Each affected app carries a `TestDiscoveryOptOut` golden set that must be updated whenever a channel is deliberately added or removed. That is the intended cost, but it is a cost.
- Rule 2 depends on cosalette's current behaviour that a void command emits no `/state` channel. A future release could change that; the tests would catch it, but the rule would need rewriting.
- Rule 3 produces four Home Assistant entities for wallpanel-control's display (two sensors, two controls) where a single `light`-style composite would produce one. The names are disambiguated, but it is more entities than an ideal modelling would need.
- The rule is longer than 'annotate or opt out', and an author who skips it will still reach for the blanket flag.

_2026-09-10_
