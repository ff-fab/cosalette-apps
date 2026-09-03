# Enhancement Proposal: event-driven publication for expanded entities

**Status:** proposed — upstream ask against cosalette; no downstream fix worth building
**Raised by:** cosalette-apps, from beads `cap-a2e` (backlog follow-up out of the
wiz2mqtt epic `cap-10u`)
**Verified against:** cosalette 0.6.3, installed source read directly
(`_app/_stream.py`, `_app/_lifecycle.py`, `_registration/_model.py`,
`_registration/_validation.py`, `_wiring/_context.py`, `_wiring/_resolution.py`,
`_runners/_telemetry_runner.py`, `_runners/_telemetry_types.py`,
`_wiring/_discovery.py`) plus `cosalette ai help` for `telemetry`, `multi-device`,
`triggerable`, `sub-entities`
**Implementation lands:** in the cosalette framework repository, **not here**. This
document is the decision record the gate task consumes; cosalette-apps writes no code
against it until a release carrying the change is on PyPI.

## Context

Two apps in this monorepo bridge **push-capable** hardware to MQTT: jeelink2mqtt (a
JeeLink USB receiver that emits a LaCrosse frame whenever a sensor transmits) and
wiz2mqtt (14 WiZ bulbs that push a pilot update over UDP whenever their state changes).
Both expose one MQTT entity per configured device, registered through a callable
`NameSpec` — `name=lambda s: {...}` — which cosalette expands at bootstrap into one
registration per device (`cosalette ai help multi-device`).

Expansion works. What does not exist is a way for an **expanded** entity to publish
because something happened. Every expanded entity in cosalette 0.6.3 publishes on a
tick: `@app.telemetry` on `interval=`/`schedule=`, `@app.device` on its own
`ctx.sleep()` loop. The push already arrives — into an adapter cache — and then both
apps wait for the next tick to notice.

`cap-a2e` records this as framework work. It is explicitly a backlog item: it did not
block the wiz2mqtt migration and does not block anything today.

## Current behaviour, with evidence

### wiz2mqtt — the push lands in a cache and waits up to 5 s

`WizBulbAdapter` registers a push callback per bulb and writes the parsed state into
`self._state_cache`
(`apps/wiz2mqtt/packages/src/wiz2mqtt/adapters/wizlight.py:106-118`). The callback
publishes nothing — it cannot; it has no `DeviceContext`. Publication happens on the
per-bulb telemetry tick:

```python
_TICK_INTERVAL_SECONDS = 5.0
"""Per-bulb poll cadence; ``get_state`` is push-cache-cheap most ticks."""
```

— `apps/wiz2mqtt/packages/src/wiz2mqtt/main.py:20-24`, feeding
`@app.telemetry(name=_bulb_map, interval=_TICK_INTERVAL_SECONDS, publish=OnChange())`
at `main.py:69-77`. `get_state` returns the cached value unless the last push is older
than 60 s, in which case it falls back to a live poll
(`adapters/wizlight.py:33-38`, `:127-133`).

The cost is not broker traffic — `publish=OnChange()` already suppresses identical
retained payloads. The cost is **latency** (0–5 s, mean 2.5 s, between a bulb changing
and Home Assistant seeing it) and **wakeups** (14 bulbs × 0.2 Hz = 2.8 handler
invocations per second, in steady state producing nothing).

### jeelink2mqtt — a stream caches, and a 1 Hz device loop drains the cache

jeelink2mqtt already uses the framework's push primitive. `@app.stream` ingests decoded
frames (`apps/jeelink2mqtt/packages/src/jeelink2mqtt/main.py:106-157`), and having
calibrated a reading it does exactly what the wiz2mqtt adapter does — caches it:

```python
# Cache the calibrated reading — the sensor's own
# per-sensor device (sensor_entity) publishes it.
state.record_calibrated_reading(name, calibrated, now)
```

— `main.py:143-145`. The publishing entity is a separate, expanded `@app.device` that
polls that cache once a second:

```python
while not ctx.shutdown_requested:
    await ctx.sleep(1.0)
    await _receiver.sensor_entity_tick(ctx, config.name, settings, state)
    yield
```

— `main.py:182-185`. Because the tick cannot know whether the cached reading is one it
has already published, the app carries its own dedup bookkeeping: two dicts on the
shared state (`state.py:61-73`, `last_publish_time` and `last_published_reading_at`)
and the freshness/heartbeat comparison in `receiver.py:120-153`, including a comment
explaining why the comparison must use the calibration timestamp rather than the
publish wall-clock. That is roughly 35 lines of app code whose entire purpose is to
recover, one tick later, information the stream handler had in hand.

The `@app.stream` handler itself is event-driven and publishes immediately — see
`publish_raw_diagnostic` at `main.py:127`, which writes `jeelink2mqtt/raw/state` per
frame. The asymmetry is precisely the gap: **the single, unexpanded stream entity can
publish on an event; the expanded per-sensor entities cannot.**

### The other seven apps do not have this problem

airthings2mqtt, gas2mqtt, vito2mqtt and wallpanel-control are static-registry pollers
of pull-only hardware. caldates2mqtt is expanded (`name=_calendar_map`) but cron-driven
by nature (`schedule=lambda cal: cal.schedule`,
`apps/caldates2mqtt/packages/src/caldates2mqtt/main.py:92-94`) — a calendar has no push
channel. velux2mqtt is expanded (`name=_cover_map`) but its covers are GPIO-driven with
time-based position estimation and no upstream notification. suncast has no MQTT entity
surface of this shape. **Two of nine apps benefit; seven are untouched.**

## Why the existing escape hatches do not close the gap

Four mechanisms look like they should, and each fails for a reason that is checkable in
the 0.6.3 source rather than a matter of taste.

**`@app.stream` cannot expand.** `_StreamRegistration` carries `name: str` and no
`name_spec` field (`_registration/_model.py:200-218`), where the device, telemetry and
command registrations all carry one (`:116`, `:147`, `:179`). The decorator signature
agrees: `name: str | None = None` (`_app/_stream.py:37`). One stream, one topic.

**Even if it could, streams are invisible to discovery.** The `@app.stream` docstring
records the applicability judgement: "Stream registrations are intentionally absent
from the generated AsyncAPI document" (`_app/_stream.py:102`, citing ADR-045's
2026-08-07 amendment), and `_app/_asyncapi.py` contains no stream handling. Runtime HA
discovery builds its payloads from `App.asyncapi()` over the post-expand registry
(`_wiring/_discovery.py:1-14`). So a design that turned expanded entities into streams
would publish state and **zero** discovery configs — which is the ADR-004 adoption path
this repo just committed to, and which `cap-hpa` and `cap-2qg` are queued to complete.

**Streams also collide with commands on the same name.** `colliding_names` puts stream
names in the collision set for every registry type
(`_registration/_validation.py:59-87`); only telemetry + command may share a name.
wiz2mqtt depends on that exemption — `_bulb_map` is used twice, once for
`@app.command` and once for `@app.telemetry` (`wiz2mqtt/main.py:44`, `:70`, with the
reason spelled out at `:86-88`). The same rule is why wiz2mqtt cannot simply move to
`@app.device` and run its own event loop: `_COLLIDE_EXTRA["device"] = ("tel", "cmd")`,
so a per-bulb device would collide with the per-bulb `/set` handler.

**`triggerable=True` is MQTT-only.** It is the right shape — the runner sleeps "until
the next cycle, woken early by trigger or shutdown"
(`_runners/_telemetry_runner.py:397-415`), and `_TriggerSlot.arm` already coalesces a
pending trigger (`_runners/_telemetry_types.py:106-129`) — but the only thing that arms
a slot is an inbound `{prefix}/{device}/set` message
(`_wiring/_context.py:312-345`). For wiz2mqtt that topic is already owned by the
per-bulb command handler; for jeelink2mqtt it would mean the app publishing an MQTT
message to its own broker to tell itself a serial frame arrived.

**`publish=OnChange()` is orthogonal.** It suppresses duplicate payloads after the
handler has run. It does not make the handler run sooner, and it does not remove a
wakeup.

## What is actually missing

One thing: **an in-process way to arm an expanded entity's existing trigger slot.**

The machinery is already there and already per-entity. `TriggerConfig.build` creates
`slots: dict[str, _TriggerSlot]` keyed by registration name
(`_wiring/_context.py:213-230`), and it is called at `_app/_lifecycle.py:361`, well
after `expand_name_specs` at `:217` — so the slots are keyed by **expanded** names
already. What does not exist is any arming path other than the MQTT proxy.

## Proposed design

### Option A (recommended) — a local trigger source and an injectable notifier

Widen `triggerable=` from `bool` to accept a trigger-source declaration, and expose the
arming side as an injectable handle.

```python
# composition root — wiz2mqtt
@app.telemetry(
    name=_bulb_map,
    interval=60,  # now a heartbeat/fallback, not the publish path
    triggerable=cosalette.Trigger(mqtt=False, local=True),
    publish=cosalette.OnChange(),
)
async def bulb_entity(
    ctx: cosalette.DeviceContext,
    config: BulbConfig,
    port: WizBulbPort,
    state: SharedState,
) -> dict[str, object] | None:
    return await bulb_entity_tick(ctx, config, port, state)
```

```python
# the arming side — anywhere DI reaches
@app.state
def shared_state(notify: cosalette.EntityNotifier) -> SharedState:
    return SharedState(notify=notify)

# wiz2mqtt's push callback, today a pure cache write:
def _on_push(parsers):
    state = _parse_state(parsers)
    if state is not None:
        self._state_cache[ip] = state
        self._last_push_at[ip] = time.monotonic()
        self._notify(self._name_for(ip))   # ← arms that bulb's slot; coalesces
```

`EntityNotifier` is a callable taking an expanded entity name. It sets the slot's
`asyncio.Event`; the runner's existing `_sleep_or_trigger` path wakes the handler, and
everything downstream of the handler — `publish=`, `state_model=` validation,
availability, persistence, error publication — is untouched, because the handler runs
through the identical cycle it runs on a tick.

`interval=` stays required and becomes the heartbeat/fallback: the guarantee that a
retained state topic is refreshed even if the device never pushes again, and the poll
that detects a dead push subscription. That preserves the wiz2mqtt staleness re-check
and the jeelink2mqtt heartbeat behaviour without either app tracking it by hand.

`TriggerPayload` gains a way to distinguish a local wake from an MQTT trigger and a
scheduled run (a third source, or `raw is None and is_triggered`) — exact shape is an
upstream call.

**Why this is the smallest change:** slots, coalescing, wake-early sleeping and the
per-entity keying already exist and are already post-expansion. The new surface is a
trigger-source declaration, a DI provider, and a thread-safe `set()`.

### Option A2 — a declarative `wake=` callable

`@app.telemetry(name=..., wake=lambda cfg: cfg.event)` — the framework awaits a
per-entity awaitable alongside the interval sleep. More declarative, but it pushes
event ownership into app code, gives the framework no name-validation point, and is
awkward to test with `fake_clock`. Recorded, not recommended.

### Option B (rejected as the primary route) — make `@app.stream` expandable

`@app.stream(name=<NameSpec>, key=<item -> name>)`, with the framework demultiplexing
one `StreamablePort[T]` across expanded entities. Conceptually the cleanest fit for
jeelink2mqtt, and it would let the receiver publish per-sensor state directly. It needs
two prerequisites first, both verified above: streams must enter the AsyncAPI document
(or discovery silently stops), and the stream/command name collision must be relaxed
(or wiz2mqtt cannot use it at all). It also needs a routing key that can consult mutable
runtime state — jeelink2mqtt resolves frames through a registry that its own MQTT
mapping commands mutate at runtime. Worth revisiting as a consolidation once Option A
has proved the semantics; not worth blocking on.

### Alternatives considered and why they lose

| Alternative | Why it loses |
| --- | --- |
| Keep polling (status quo) | Works, and is the honest baseline. Costs latency (mean 2.5 s wiz2mqtt, 0.5 s jeelink2mqtt), a per-entity wakeup budget that scales linearly with device count, and ~35 lines of dedup bookkeeping in jeelink2mqtt |
| Lower the tick interval | Latency falls linearly, wakeups rise linearly. At 14 bulbs a 1 s tick is 14 invocations/s to make a push visible within 1 s. Buys nothing the event already knows |
| Debounce/`OnChange()` only | Already in place in both apps. Suppresses duplicate payloads; changes neither latency nor wakeups |
| Per-app workaround (`@app.device` + own event loop) | Blocked for wiz2mqtt by the device/command name collision (`_registration/_validation.py:59-63`). Possible for jeelink2mqtt, but it is what the app already does, and it re-derives freshness state the framework could hand over |
| App publishes via a raw MQTT client from the push callback | Bypasses `state_model` validation, availability, `OnChange`, ADR-048 retained cleanup and the topic router. Reintroduces exactly the ad-hoc `ctx.publish()` pattern `cap-ayy` removed from jeelink2mqtt |

## Validation criteria

"Works" means the assertions below hold. They are written to be implementable as
upstream tests against the existing fixtures (`mock_mqtt`, `fake_clock`,
`device_context`, `AppHarness`, `assert_discovery_topics_published`).

### Core behaviour

1. **Slots exist per expanded entity.** For a telemetry registration with a callable
   `name=` yielding _n_ names and local triggering enabled,
   `set(TriggerConfig.build(resolved).slots) == set(expanded_names)` and its length is
   _n_.
2. **A local notify publishes without the clock advancing.** With `fake_clock` and
   `interval=3600`, notifying entity `"kitchen"` at virtual t=0 results in exactly one
   publish to `{prefix}/kitchen/state` with virtual time still at t=0 (± one loop
   iteration). This is the assertion the whole proposal exists for.
3. **Only the named entity wakes.** Notifying `"kitchen"` in a 3-entity expansion
   produces publishes on `{prefix}/kitchen/state` only; the other two record zero
   handler invocations.
4. **Coalescing.** _k_ notifications delivered while the handler is in flight result in
   exactly one additional run, mirroring the existing MQTT-trigger coalescing test.
5. **Unknown names fail loudly.** Notifying a name that is not in the slot map raises a
   named exception (or logs at WARNING and returns a falsy result) — never a silent
   no-op. The chosen behaviour is asserted, not left to implementation.
6. **Thread safety.** A notification issued from `asyncio.to_thread` is delivered
   exactly once and does not raise.

### Parity — nothing about a woken run differs from a ticked run

7. `publish=OnChange()` still gates: two notifications yielding an identical payload
   produce one retained publish.
8. `state_model=` validation applies identically — a woken run returning a
   non-conforming payload raises `ReturnValidationError` and publishes to the error
   topic.
9. Availability is unchanged: `ctx.mark_unavailable()` / `mark_available()` from a woken
   run behave as from a ticked run, retained on `{prefix}/{name}/availability`.
10. Topics are unchanged: a woken expanded entity publishes to `{prefix}/{name}/state`,
    **not** to a sub-topic. Asserted through `AppHarness`, not by inspecting internals.

### Non-regression — the ADR-004 discovery path must not move

11. `app.asyncapi()` output is identical with and without local triggering enabled for
    the same registrations (byte-for-byte, or field-for-field after JSON load).
12. `assert_discovery_topics_published` passes unchanged for an app that adopts local
    triggering, and the retained `homeassistant/.../config` topic set is identical to
    the same app without it.
13. `consumer()` annotations are unaffected: the generated HA discovery payload for a
    field carrying `consumer(display_name=..., unit=..., state_class=...)` is identical
    before and after. Cadence and annotation live on different axes and must stay
    there.

### Backward compatibility

14. `triggerable=True` keeps its current meaning — MQTT-triggerable — and the router's
    subscription set for an existing app is unchanged.
15. Every existing registration form still resolves: no app that does not opt in sees
    any behavioural change. Demonstrated by the existing upstream suite passing
    unmodified.
16. The registration-time guards in `_wiring/_resolution.py:202-207`
    (`triggerable` + `group=`, `triggerable` on a root device) either still apply or
    have a documented, tested new answer for the local source (see open question 4).

### Definition of done for an upstream release

- A cosalette release on PyPI (0.7.x, or a 0.6.x minor if the change is purely
  additive) carrying the API.
- `cosalette ai help triggerable` and `cosalette ai help multi-device` document the
  local source, and `cosalette ai init` ships the updated
  `cosalette.instructions.md`.
- The registry snapshot / `cosalette manifest --table` shows an entity's trigger
  sources, so an operator can see whether an entity is event-driven.
- Downstream acceptance, verified in this repo before the gate closes: jeelink2mqtt
  publishes a sensor's state within the same virtual tick as the frame that produced it
  (asserted with `fake_clock`, no time advance), and wiz2mqtt publishes a bulb's state
  from a simulated push without the 5 s tick elapsing — both in integration tests using
  the existing app fixtures.

## Pros and cons

### For the framework

**Pros**

- Reuses machinery that already exists and is already keyed by expanded name; the new
  surface is a trigger-source declaration, a DI provider and a thread-safe `set()`.
- Closes a real asymmetry: `@app.stream` is event-driven but singular; expanded
  entities are plural but tick-driven. Nothing today is both.
- Purely additive and opt-in. `triggerable=True` keeps its meaning; apps that do not
  ask for it see no change.
- Keeps the publish path single: everything still flows through the handler cycle, so
  `publish=`, `state_model=`, availability, persistence and error publication cannot
  drift between "ticked" and "pushed" publications.
- Removes a whole class of downstream bookkeeping (freshness comparison against a
  cached reading) that every push-capable app otherwise reinvents.

**Cons**

- **New public API surface** on the busiest decorator. `@app.telemetry` already carries
  `interval`, `schedule`, `group`, `publish`, `persist`, `retry`, `backoff`,
  `circuit_breaker`, `timeout`, `triggerable`, `enabled`, `state_model`,
  `payload_model` — thirteen axes already. Widening `triggerable=` from `bool`
  to a union makes an already-overloaded parameter carry more.
- **`triggerable=` becomes two concepts under one name** (an MQTT subscription and an
  in-process wake). A separate parameter avoids that but grows the surface further; a
  genuine trade with no free answer.
- **A new escape hatch from declarative composition.** A notifier that can be injected
  anywhere is a handle that can be called from anywhere, including places that should
  not be publishing. The domain-purity rule ("domain never imports cosalette") needs to
  survive it.
- **Storm exposure.** A chatty device can arm a slot continuously. Coalescing bounds the
  queue, not the handler rate; a min-interval knob may be needed, which is more surface
  again.
- **Thread-safety is now load-bearing.** Push callbacks from serial/BLE/HID adapters may
  not run on the event loop, so the arming path must use `call_soon_threadsafe` and say
  so in the contract.
- **Testing story must be explicit**, or downstream apps will patch `asyncio.Event`
  and break the `fake_clock` rules the testing guidance already warns about.

### For this repository as a consumer

**Pros** — two apps get lower latency, fewer wakeups and less code (quantified below);
no migration is forced on the other seven; the `consumer()` annotations and
`docs/schema.yaml` pipeline are untouched.

**Cons** — a version-pin bump across every app that adopts (`cosalette>=0.7,<0.8` if it
lands as a minor), which is a full `task pre-pr` cycle per app even for apps that gain
nothing; and two apps acquire a second publication trigger, so "why did this publish?"
becomes a two-answer question during debugging. Both are small, and both are real.

### Migration burden

Effectively none, because the change is additive and opt-in:

- Seven apps: no change. No `consumer()` annotation moves, no `state_model` changes, no
  topic changes, no `docs/schema.yaml` regeneration.
- wiz2mqtt: one decorator argument, one notifier threaded from the composition root into
  `WizBulbAdapter`, `_TICK_INTERVAL_SECONDS` raised from 5 s to a heartbeat cadence.
- jeelink2mqtt: the larger change, and possibly a conversion of `sensor_entity` from
  `@app.device` to `@app.telemetry` (open question 5). Deletes the freshness
  bookkeeping.

## What cosalette-apps gains

Written from the downstream side, and deliberately not overstated.

**jeelink2mqtt** — the biggest win, and it is a code-deletion win.
`sensor_entity` (`main.py:160-185`) stops being a 1 Hz poller and becomes an
event-driven publisher woken by the stream handler at `main.py:145`, where the reading
is calibrated. Deleted: `last_publish_time` and `last_published_reading_at`
(`state.py:61-73`) and the freshness/heartbeat comparison in `receiver.py:120-153` —
roughly 35 lines whose only job is to re-derive, one tick later, what the stream
already knew. Latency from frame to retained state drops from a mean of 0.5 s to
approximately zero. Steady-state wakeups drop from _n_ per second to one per received
frame plus the heartbeat, which for LaCrosse sensors reporting every ~30 s is
one to two orders of magnitude fewer.

**wiz2mqtt** — the latency win. A bulb changed at the wall switch or from the WiZ app
currently reaches Home Assistant 0–5 s later (`main.py:20-24`); with an event-driven
publish it reaches it as fast as the push does. `_TICK_INTERVAL_SECONDS` can then rise
to the adapter's own 60 s staleness threshold
(`adapters/wizlight.py:33-38`), cutting per-bulb handler invocations from 2.8/s across
14 bulbs to about 0.23/s — a ~92% reduction in wakeups.

**MQTT and broker load: honest accounting.** Broker traffic barely moves. Both apps
already gate publication — wiz2mqtt with `publish=OnChange()` (`main.py:72`),
jeelink2mqtt with its hand-rolled freshness check — so the broker is not currently
seeing per-tick republishes. What falls is in-process work (timer wakeups, adapter cache
reads, `OnChange` payload comparisons) and end-to-end latency. Anyone selling this as an
MQTT-traffic reduction is selling the wrong benefit.

**Beads impact — also honest.** `cap-a2e` has no `blocks` or `depends on` edges in the
graph today; it unblocks nothing directly, and closing it is not a prerequisite for any
open task. Its real relationship to the ADR-004 discovery chain (`cap-egy` → `cap-hpa`,
`cap-2qg`, `cap-8sw`) is a **constraint, not a dependency**: validation criteria 11–13
exist so that whatever ships for `cap-a2e` cannot disturb the runtime-discovery path
those tasks are adopting. Option B is rejected as the primary route precisely because it
would have. If the two land in either order, neither should move the other.

`cap-fux` (generated group entities for the six multi-bulb groups) is a separate
upstream ask — a `[[groups]]` table the settings/TOML-inventory validator rejects today
— and shares only its wiz2mqtt origin with this one. It is not unblocked by this work.

## Out of scope

Explicitly not asked for here:

- Making `@app.stream` expandable, or putting streams into the AsyncAPI document
  (recorded as Option B; a separate ask if anyone wants it).
- Any change to `@app.command` dispatch or to the name-collision rules.
- A general inter-entity event bus or pub/sub between handlers. This is one signal —
  "publish now" — to one named entity.
- Any change to HA/openHAB discovery generation, `consumer()`, `docs/schema.yaml`,
  `schema:generate` or `schema:check`. Parity is a requirement here, not a target.
- Generated group/composite entities (`cap-fux`) and array-item consumer annotations
  (`cap-30z`).
- A rate limiter or publication QoS scheduler. Coalescing is in scope only because it
  already exists.
- Any change to how this repo's apps are deployed. No app adopts anything until an
  upstream release exists.

## Risks and open questions

1. **Where does an adapter get the notifier?** Adapters are constructed by the framework
   from a class path or a factory taking `Settings`
   (`apps/jeelink2mqtt/.../main.py:46-48`). Whether DI can reach an adapter factory in
   0.6.3 is **unverified** — the pattern shown above routes the notifier through an
   `@app.state` factory into shared state instead, which is known to work but is
   indirect. Upstream should decide the intended path.
2. **Thread safety of the arming call.** pywizlight's push arrives on the event loop
   (asyncio datagram protocol), but serial and BLE adapters elsewhere may not. Whether
   `EntityNotifier` must be loop-affine or thread-safe is a contract decision, and
   criterion 6 exists to pin it. Not verified for any adapter but wiz2mqtt's.
3. **Storm control.** Should the framework offer a minimum interval between woken runs,
   or is coalescing plus `publish=OnChange()` enough? Unmeasured — no burst data exists
   for either app.
4. **Root (unnamed) entities.** `triggerable=True` is rejected on root devices because
   there is no topic segment to subscribe to (`_wiring/_resolution.py:205-207`). A local
   wake needs no topic segment, so the restriction may not apply. Open.
5. **Does `@app.device` get this too, or only `@app.telemetry`?** The trigger slots live
   on telemetry registrations only (`_wiring/_context.py:225-228`). jeelink2mqtt's
   `sensor_entity` is an `@app.device`, so a telemetry-only feature forces a conversion.
   That conversion looks feasible — the handler returns nothing and publishes through
   `ctx`, which `@app.telemetry` supports by returning `None` — but it is **unverified**
   and would need its own downstream task.
6. **Interaction with `group=`.** `triggerable=` and `group=` are mutually exclusive
   today (`_wiring/_resolution.py:202-204`). Whether a local source inherits that
   exclusion is undecided; neither affected app uses `group=`.
7. **Health reporting.** Whether a woken run counts toward the health reporter and
   restart accounting exactly as a ticked run does is **unverified** — the runner path
   is shared, which suggests yes, but it was not read end to end.
8. **Is there already an undocumented in-process arming path?** The public export list,
   the wiring modules and the trigger runner were read and none was found, but not every
   module in the installed package was read. Stated as verified-to-that-extent.

## Tracking

`cap-a2e` (P3, open, labels `cosalette`, `follow-up`, `framework`, `wiz2mqtt`) is the
tracking bead. Per this repo's convention the bead holds no decision logic — this
document does — and closes when a cosalette release carrying the change is on PyPI and
the affected apps' pins can be bumped. Nothing in this repository changes before then.
