# Enhancement Proposal: Home Assistant discovery for STREAM-archetype apps

**Status:** Proposed
**Raised by:** cosalette-apps (cap-dnw — jeelink2mqtt HA discovery investigation)
**Verified against:** cosalette 0.5.9, `cosalette._app._stream`, `cosalette._runners._stream_types`,
`cosalette._schema._loader_helpers`, `cosalette._schema._asyncapi`,
`cosalette._schema._consumer_gen`, `cosalette._context._device_context`

## Context

cosalette ships a static, build-time Home Assistant MQTT discovery generator
(`cosalette schema ha-discovery`, implemented by `HaDiscoveryGenerator` in
`cosalette._schema._consumer_gen`). It walks the AsyncAPI schema registry built from
decorator introspection (`build_app_asyncapi` in `cosalette._schema._asyncapi`) and turns
each channel's `x-cosalette-consumer` annotation into a `homeassistant/.../config` publish
payload. This works well for the `telemetry`, `command`, and `device` archetypes, all of
which are eligible for schema/consumer annotation.

jeelink2mqtt (a cosalette-apps consumer) is built on the **STREAM** archetype
(`@app.stream`, ADR-042/ADR-045). It receives per-sensor readings whose ephemeral
hardware IDs are resolved to configured logical names at runtime (auto-adopt, see
cosalette-apps' own ADR-002), and publishes per-sensor topics
(`{name}/state`, `{name}/availability`) dynamically as sensors are discovered. When we
tried to give jeelink2mqtt the same HA discovery support the other five cosalette-apps
integrations have (airthings2mqtt, gas2mqtt, velux2mqtt, vito2mqtt, wallpanel-control),
we found the STREAM archetype has no path into that pipeline at all — not a missing
annotation, but a structural gap. This document lays out that gap and asks the framework
maintainers to consider closing it.

## Finding 1 — STREAM registrations never reach the AsyncAPI schema registry

`build_app_asyncapi()` (`cosalette/_schema/_asyncapi.py`) builds the entire schema
document by iterating exactly three registration lists on the `App` instance:

```python
for reg in app.telemetry_registrations: ...   # kind="telemetry"
for reg in app.commands: ...                   # kind="command"
for reg in app.devices: ...                     # kind="device"
```

`app._streams` (the list `_StreamMixin.stream()` / `add_stream()` appends
`_StreamRegistration` entries to — `cosalette/_app/_stream.py`) is never read by this
function. There is no fourth loop, no `kind="stream"` branch, nothing. Confirmed by
reading the full body of `build_app_asyncapi()`: it only ever emits channels tagged
`"telemetry"`, `"command"`, or `"device"`.

This is corroborated independently in `cosalette/_schema/_loader_helpers.py`:
`_validate_archetype()` explicitly asserts that `x-cosalette-archetype` must be one of
`{"telemetry", "command", "device"}` — "stream" is not a member of that set, so even a
hand-authored schema fragment claiming `x-cosalette-archetype: stream` would fail
loader validation.

**Consequence:** a STREAM handler can never produce a channel with a
`x-cosalette-consumer` annotation, because it never produces a channel at all. The
`HaDiscoveryGenerator` has nothing to walk for it. This isn't a gap in the discovery
generator specifically — it's upstream, in schema generation.

## Finding 2 — `_StreamRegistration` carries no per-item schema/consumer metadata

`_StreamRegistration` (imported from `cosalette._registration` and used by
`_app/_stream.py`) records `name`, `func`, `injection_plan`, `enabled_spec`, `is_root`,
`maxsize`, `backpressure`, `summary`, `behavior`, `effects` — no `state_model`,
`payload_model`, or consumer-metadata field comparable to what
`telemetry`/`command`/`device` registrations carry. Even if a future
`build_app_asyncapi()` grew a fourth loop over `app._streams`, there is currently no
field on the registration to hang a per-item (let alone per-*discovered-instance*)
schema on. STREAM handlers process a `Stream[T]` of one static item type `T` — but
jeelink2mqtt's discovery problem is one level below that: many runtime *instances*
(one per physical sensor) share that one static type, and HA discovery needs a
distinct `unique_id`/state-topic per instance, not per type.

**We could not find, anywhere in the installed package, a mechanism — static or
runtime — for a framework consumer to register or emit per-instance metadata for
dynamically-discovered sub-entities.** If one exists outside the modules we inspected,
this proposal is written without knowledge of it; we grounded this entirely in
`_app/_stream.py`, `_runners/_stream_types.py`, `_schema/_loader_helpers.py`,
`_schema/_asyncapi.py`, and `_schema/_consumer_gen.py`.

## Finding 3 — `DeviceContext.publish()` cannot reach the shared discovery namespace

Home Assistant discovery payloads are conventionally published to a namespace shared
across *all* integrations on a broker (default `homeassistant/...`), not scoped to a
single app. `cosalette._context._device_context.DeviceContext` computes:

```python
self._topic_base = topic_prefix if is_root else f"{topic_prefix}/{name}"
```

and both `publish_state()` and `publish()` build their topic as
`f"{self._topic_base}/..."` — always underneath the app's own prefix
(`jeelink2mqtt/...`). There is no public method to publish to an arbitrary absolute
topic outside that prefix. The only route we found is the private `ctx._mqtt` attribute
(`cosalette._mqtt.MqttPort.publish(topic, payload, ...)`, which *does* accept an
arbitrary topic string) — but that means bypassing the public port abstraction
entirely, which is exactly the boundary ADR-006 (Protocol-based ports) exists to
enforce on the framework side, and ADR-003 (hexagonal architecture) enforces on the
cosalette-apps side.

**Consequence:** even an app willing to hand-roll its own discovery-payload
construction and publish it imperatively at runtime (bypassing the schema/consumer
pipeline entirely) has no supported way to land that payload in the shared HA
discovery namespace without reaching into a private attribute.

## Options

### (a) Additive runtime/imperative discovery-publishing helper

Add a public method — e.g. `DeviceContext.publish_ha_discovery(component, object_id,
config, *, discovery_prefix="homeassistant")` — that publishes a
`{discovery_prefix}/{component}/{app.name}_{object_id}/config` payload outside the
app's own topic prefix, callable at any point in a handler's lifetime (not just at
schema-generation time).

- **Additive vs. breaking:** additive. New method, no change to existing behavior.
- **Shape:** a thin method on `DeviceContext` (or a small `HaDiscoveryPort`/mixin) that
  builds the topic directly and delegates to the existing `MqttPort.publish()`, with
  the payload dict supplied entirely by the caller (framework does not infer
  component/unit/device_class at runtime — that inference logic in
  `_consumer_gen._infer_component()` is schema-driven and has no runtime equivalent
  without Finding 2's per-instance metadata).
- **Tradeoffs:** small, low-risk framework surface; but it hands the caller full
  responsibility for payload correctness — no schema validation, no drift detection
  between what's declared and what's published, and it establishes a second,
  parallel discovery path (static schema-driven + ad hoc runtime) that the framework
  does not reconcile. Maintenance burden is low but consistency guarantees are weaker
  than the static pipeline's.

### (b) Extend the STREAM archetype's contract for per-entity metadata

Add an optional per-item metadata callback/model to `@app.stream` /
`_StreamRegistration` — e.g. a `consumer_for: Callable[[T], ConsumerMetadata]`
parameter — so the framework itself could, in principle, generate discovery payloads
for stream items using the same `consumer()`/`ConsumerMetadata` shapes
telemetry/command/device already use, evaluated per-instance instead of once at
schema-build time.

- **Additive vs. breaking:** additive at the decorator/registration level (new
  optional parameter); but *using* it to generate discovery still requires solving
  Finding 1 (a stream-aware branch in schema/AsyncAPI generation or a fully separate
  runtime-generation path) and Finding 3 (a supported publish route). In isolation,
  this option only fixes Finding 2.
  Also: since `x-cosalette-consumer` and the AsyncAPI channel model are currently
  defined around *static* channels, letting a stream emit a variable, runtime-sized
  set of "channels" is a real shape mismatch — the AsyncAPI document format itself may
  need a way to express "one channel, many discovered instances," which we consider
  a design question the maintainers are better positioned to resolve than we are.
- **Shape:** substantial — touches `_StreamRegistration`, `_app/_stream.py`,
  `_schema/_asyncapi.py`, and `_schema/_consumer_gen.py`.
- **Tradeoffs:** most consistent with the framework's existing declarative-schema
  philosophy long-term, but the largest implementation lift of the options that
  actually solve the problem, and the AsyncAPI-shape question above is unresolved.

### (c) Registry/lifecycle-hook (on-first-seen callback) model

Add a callback hook — e.g. `ctx.on_first_seen(item_key, callback)` or an
`on_discover` parameter to `@app.stream` — invoked once per distinct runtime instance
(keyed by whatever the app considers a stable identity, e.g. jeelink2mqtt's resolved
sensor name), which the app populates with its own discovery-payload construction and
publish call.

- **Additive vs. breaking:** additive.
- **Shape:** moderate — a bookkeeping helper (dedup by key, fire-once semantics) layered
  on top of option (a)'s publish primitive. Framework provides the "when," app
  provides the "what" (still no framework-side inference of component/unit/etc.,
  same limitation as (a)).
- **Tradeoffs:** meaningfully reduces boilerplate apps would otherwise hand-roll
  themselves (dedup/first-seen tracking) without asking the framework to solve
  schema inference for dynamic instances. Still leaves discovery-payload correctness
  entirely on the app, and still needs Finding 3 solved (some publish route to the
  shared namespace) — this option is really "(a) plus a convenience wrapper," not a
  standalone alternative.

### (d) Unify static and runtime discovery under one mechanism

Redesign `HaDiscoveryGenerator` so the same code path handles both build-time schema
walking and runtime per-instance emission — e.g. by making discovery generation a
method the framework calls both once at schema-build time (over static registrations)
and imperatively at runtime (over stream items with per-instance keys from option (b)).

- **Additive vs. breaking:** likely breaking, or at minimum needs care.
  `x-cosalette-consumer`, `HaDiscoveryGenerator.generate()`, and the CLI's
  `schema ha-discovery` subcommand are all currently defined around a single static
  pass over a fixed `SchemaRegistry`. Making that dual-mode (static-registry input
  *or* runtime-instance input) changes the shape of the internal API surface that
  `_consumer_gen.py` exposes, even if the CLI-facing behavior for existing apps stays
  the same. We can't say with confidence from the source alone whether this could be
  done without touching `x-cosalette-consumer`'s documented format — flagging this as
  unconfirmed rather than asserting either way.
- **Shape:** largest of all options — touches schema generation, AsyncAPI building,
  and the discovery generator together.
- **Tradeoffs:** most architecturally clean end state (one discovery mechanism, not
  two parallel ones as in (a)/(c)), but highest risk and effort, and the breaking-ness
  is genuinely uncertain without maintainer input on how attached
  `x-cosalette-consumer` consumers currently are to the static-only assumption.

### (e) Pluggable inference heuristics as a framework feature

Let apps register a callable that infers HA `component`/`device_class`/`unit`/etc.
from a runtime item's type/value (e.g. `T -> ConsumerMetadata`), reusing
`_consumer_gen._infer_component()`'s logic but with an app-supplied fallback/override
for cases the static heuristics can't cover.

- **Additive vs. breaking:** additive.
- **Shape:** moderate — mostly reorganizing `_infer_component()` into a public,
  overridable extension point rather than a private, hardcoded `_HA_COMPONENT_MAP`.
- **Tradeoffs:** doesn't by itself solve Finding 1 or Finding 3 — it only makes
  inference reusable *if* one of (a)/(b)/(c)/(d) already provides a runtime path to
  call it from. Worth doing regardless of which other option is chosen, since it
  removes duplicated guesswork every app would otherwise reinvent, but not a
  standalone fix.

### (f) Do-nothing / status-quo baseline

Leave STREAM apps out of HA discovery entirely; document the limitation (which is
what cap-dnw did at the cosalette-apps level for jeelink2mqtt).

- **Additive vs. breaking:** no change.
- **Shape:** none.
- **Tradeoffs:** zero framework risk or maintenance cost, but every STREAM-archetype
  app in every cosalette-apps consumer permanently loses HA discovery, pushing
  consumers toward manually-configured MQTT entities or ADR-003-violating private-API
  workarounds if they want automation badly enough. Consistent with the framework's
  declarative-schema philosophy in the narrow sense that it adds nothing undeclared,
  but at the cost of a real capability gap for an entire archetype.

## Recommendation

At the cosalette-apps level, we chose the equivalent of option (f) for jeelink2mqtt
specifically (documented in `apps/jeelink2mqtt/README.md` — see cap-dnw) because
implementing any of (a)–(e) is framework work, not app work: nothing available to us
as a framework *consumer* can close Findings 1–3 from inside an app.

For the framework itself, we'd suggest (c) — a first-seen lifecycle hook built on top
of (a)'s publish primitive — as the best near-term, purely-additive step: it directly
unblocks apps like jeelink2mqtt without requiring the AsyncAPI/schema-shape questions
in (b)/(d) to be resolved first, and it's a strict subset of what (d)'s unified design
would eventually need anyway. We'd treat (e) as a good complementary addition
regardless of timing (it only ever reduces duplicated guesswork), and would leave (d)
as a longer-term direction rather than a prerequisite — it's the architecturally
cleanest end state but carries real, currently-unquantified breaking-change risk that
deserves dedicated maintainer design attention rather than being bundled with a
point fix for jeelink2mqtt's specific gap.

## Summary

| # | Finding | Impact | Suggested fix |
|---|---------|--------|----------------|
| 1 | `build_app_asyncapi()` never iterates `app._streams` | STREAM handlers produce no schema channel at all | (b)/(d) |
| 2 | `_StreamRegistration` has no per-item/per-instance consumer metadata field | Even with a schema channel, no way to express dynamic per-instance discovery data | (b) |
| 3 | `DeviceContext.publish()` is scoped to the app's own topic prefix | No supported runtime route to HA's shared discovery namespace | (a) |

## What cosalette-apps is doing

jeelink2mqtt documents HA discovery as not applicable (README, cap-dnw), mirroring the
caldates2mqtt/suncast pattern (commit `9322db1`). No workaround was implemented against
private cosalette internals (e.g. `ctx._mqtt`) — that would violate this repo's own
ADR-003 hexagonal-architecture boundary for the sake of a framework gap that belongs
upstream.

**One request on the shape of the fix.** Whatever combination of (a)–(e) the
maintainers pursue, we'd ask that the resulting public API be something a STREAM app
can adopt without reaching into `_consumer_gen.py`'s private inference tables or
`DeviceContext._mqtt` — i.e., a genuinely public, documented entry point, the same
bar the existing static `schema ha-discovery` pipeline already meets for
telemetry/command/device apps.
