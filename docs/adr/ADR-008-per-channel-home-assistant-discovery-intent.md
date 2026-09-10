---
status: Accepted
date: 2026-09-10
impact: high
tags: [architecture, mqtt, telemetry, devices, documentation]
---

# ADR-008: Per-Channel Home Assistant Discovery Intent

## Status

Accepted **Date:** 2026-09-10 | Amended **Date:** 2026-09-10

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

## Amendment (2026-09-10) — Minor

**Rationale:** cosalette 0.9.5 (upstream ADR-074) lifts the one-flag-per-registration constraint that forced Rules 2 and 3. `discoverable` is now `bool | Literal["command", "state"]` on `@app.command` / `@app.device`, so a command that publishes state can hide only its `/set` channel directly with `discoverable="state"`. The apps are unchanged today — migration is tracked separately — so this is an editorial note, not a revision of the decision.

!!! note "Editorial note (2026-09-10)"
    **The constraint behind Rules 2 and 3 is lifted from cosalette 0.9.5 (upstream ADR-074).** `discoverable` was one boolean per registration, which is why a command publishing state had to either void its handler (Rule 2) or annotate its payload model (Rule 3) to avoid taking the telemetry sensors with it. 0.9.5 widens the flag to `bool | Literal["command", "state"]` on `@app.command` / `@app.device` and their Router forms. `discoverable="state"` keeps the `/state` channel discoverable and opts only the `/set` command channel out, stating the intent directly instead of relying on handler voidness. The literal resolves to a plain per-channel boolean at document-generation time, so the emitted `x-cosalette-discoverable` extension and the ADR-073 loader are unchanged.

!!! note "Editorial note (2026-09-10)"
    **No app in this repo has migrated yet; the rules above still describe the shipped code.** vito2mqtt still uses the Rule 2 void-handler workaround, whose migration to `discoverable="state"` is tracked as cap-33eq. wallpanel-control still uses the Rule 3 `consumer()` annotation and is tracked as cap-c9v (a three-way trade — `discoverable="state"` would drop the HA control that PR #250 added, so it is not a free win). gas2mqtt (`consumption`) and jeelink2mqtt (`mapping`) are not migration candidates: their command handlers return acknowledgement dicts, but neither the `/set` command nor its paired `/state` channel is a consumer entity, so `discoverable=False` deliberately opts BOTH halves out and stays correct. Only vito2mqtt relies on the void-handler mechanism.

!!! note "Editorial note (2026-09-10)"
    **The enforcement gap is unchanged and remains the reason this ADR exists.** `cosalette schema check` still never reads `x-cosalette-discoverable`, so neither a lost sensor nor a lost opt-out fails CI on its own — whether the intent is stated with `discoverable=False`, a void handler, or the new `discoverable="state"`. Rule 5 still holds: every declaration stays locked by a `TestDiscoveryOptOut` golden set.

## Amendment (2026-09-10) — Minor

**Rationale:** cap-c9v is resolved. cosalette 0.9.5's channel-level composite (ADR-057) spans a @app.command's paired /set and /state channels, so wallpanel-control's display now surfaces as one Home Assistant light instead of four scalar entities — the ideal modelling ADR-008 named as out of reach. This records the resolution; the five rules are unchanged.

!!! note "Editorial note (2026-09-10)"
    The premise that a composite could not span a command registration's distinct payload_model and state_model (recorded against cap-c9v) is disproven — no framework change was needed. Declaring the same ha_entities() spec on BOTH DisplayCommand and DisplayState makes cosalette merge the two channels: the /state model supplies state_topic and the /set model supplies command_topic, exactly as ADR-057 already does for a device archetype's single-model channel pair.

!!! note "Editorial note (2026-09-10)"
    wallpanel-control now emits one `light` (Home Assistant template schema) carrying power and brightness. Unlike discoverable="state", the composite keeps the control PR #250 added AND collapses the entity count, so it is not the three-way trade the prior amendment described. The MQTT wire contract is unchanged: the light's templates map HA's 0-255 brightness and upper-case ON/OFF onto this app's 1-100 percent and lower-case on/off. This makes wallpanel-control the reference for a composite spanning a command's paired channels, superseding its Rule 3 consumer() annotations; vito2mqtt (Rule 2 void handler, cap-33eq) is unaffected.

### Additional Positive Consequences

- wallpanel-control's display collapses from four Home Assistant entities (two sensors, a select, a number) to one composite `light`, resolving the negative consequence above that Rule 3 produced more entities than an ideal modelling needs (cap-c9v).
