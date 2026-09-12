---
status: Accepted
date: 2026-09-06
impact: moderate
tags: [telemetry, architecture, mqtt, scheduling, lifecycle]
---

# ADR-006: Event-Driven State Publication for the Bulb Entity

## Status

Accepted **Date:** 2026-09-06 | Amended **Date:** 2026-09-12

## Context

A WiZ bulb emits an unsolicited UDP push whenever its state changes (ADR-004). Until cosalette 0.8.0 an adapter that received one had no way to tell its telemetry entity — the push callback wrote a cache and returned, and the fresh value sat there until the next scheduled tick. The first cut of wiz2mqtt compensated with a 5-second poll tick whose only job was to shorten push-to-publish latency.

cosalette 0.8.0 (upstream ADR-064..067) added the missing arming path: `triggerable=` widened to a trigger-source declaration, and an injectable `EntityNotifier` arms the same trigger slot the MQTT path would. The repo-wide adoption decision is recorded once in `docs/adr/ADR-005-event-driven-publication-adoption.md`; wiz2mqtt's adoption landed as **cap-10u.21** in commit **76950cc**. This app-scoped ADR records the local shape and the two parameter choices that are specific to wiz2mqtt.

The consumer-integration work (cap-10u.14) does not change any of this — it registers an `@app.command` for the `/set` channel and enriches the discovery metadata, but `bulb_entity` still publishes through the same handler, `OnChange()` gate and availability debounce whether it woke on the heartbeat or on a push. This ADR is written now because cap-10u.14 is the first change to touch that registration since 76950cc, and the reasoning belonged in the app's own `docs/adr/` rather than only in the repo-wide record.

## Decision

Publish `bulb_entity` state on the WiZ push, not on the poll tick. `WizBulbAdapter` is constructed with `Wiz2MqttSettings` and an injected `cosalette.EntityNotifier`; its push callback writes the state cache and then calls `notify(bulb_name)`. `bulb_entity` is registered `triggerable="local"` (no MQTT trigger topic subscribed), `publish=cosalette.OnChange()`, `interval=60.0` as a heartbeat/liveness floor deliberately equal to the adapter's `_DEFAULT_PUSH_STALENESS_THRESHOLD`, and **without** `min_interval=`.

```python
@app.telemetry(
    name=_bulb_map,
    interval=_TICK_INTERVAL_SECONDS,   # 60 s heartbeat, not the driver
    triggerable="local",               # armed in-process by EntityNotifier; no topic
    publish=cosalette.OnChange(),      # drops identical payloads
    state_model=BulbStateModel,
)
async def bulb_entity(ctx, config, port, state) -> BulbStateModel | None:
    result = await bulb_entity_tick(ctx, config, port, state)
    return BulbStateModel.model_validate(result) if result is not None else None
```

## Decision Drivers

- The bulb already signals every state change via push, so publication should follow the push rather than a poll interval
- The 5 s tick existed only to mask latency; once the push publishes, the tick can rise to a 60 s heartbeat and double as a liveness probe
- The wake is a pure in-process implementation detail, so `triggerable="local"` is correct — it subscribes no MQTT topic and adds no broker-visible control surface
- `OnChange()` already drops duplicate payloads, so a `min_interval=` storm throttle would add latency without removing any publish
- A WiZ bulb only pushes on change, so there is no push storm for `min_interval=` to bound in the first place
- The repo-wide decision (ADR-005) already commits every app with a real event source to this pattern; wiz2mqtt has the clearest event source of all of them

## Considered Options

### Option 1: Push-driven via triggerable=local + EntityNotifier, no min_interval (chosen)

Adapter injects `EntityNotifier` and calls `notify(name)` after each push cache write. `bulb_entity` is `triggerable="local"`, keeps `interval=60` as a heartbeat, gates on `OnChange()`, and sets no `min_interval=`.

- *Advantages:* State reaches MQTT within a push round-trip instead of up to a poll interval later; The poll tick drops from 5 s to 60 s and becomes a liveness probe aligned with the push-staleness threshold; `triggerable="local"` keeps the wake in-process — no MQTT topic, no public surface; One publication path: a push and a heartbeat both run the same handler, `OnChange()` gate and availability debounce
- *Disadvantages:* Two arming paths per entity, so a missing or misplaced `notify()` call is a silent latency regression, not a loud failure; Relies on the push return path actually working (ADR-004 host-networking requirement)

### Option 2: Keep the 5-second poll tick as the publication driver

Do not adopt the trigger. `bulb_entity` stays purely scheduled at a short interval; the push callback keeps only warming the cache so the next tick has fresh data.

- *Advantages:* One arming path, trivially predictable — everything happens on the tick; No dependency on the push return path for timely publication; No new framework surface to reason about
- *Disadvantages:* Latency is bought with poll frequency, which is the wrong currency — every bulb is re-read every 5 s whether or not anything changed; Still up to 5 s between a change and its retained topic, versus sub-second on push; Diverges from the repo-wide ADR-005 adoption that every event-bearing app now follows; The push callback stays a dead end: the adapter knows the value changed and cannot say so

### Option 3: Adopt the trigger and also set min_interval as a storm throttle

Same as the chosen option but with `min_interval=` (e.g. 5-15 s) to bound trigger-initiated run starts.

- *Advantages:* Bounds worst-case handler invocation rate if a bulb ever pushed pathologically often; Matches the parameter set vito2mqtt and airthings2mqtt use
- *Disadvantages:* `OnChange()` already coalesces duplicates, so the throttle removes no publish — it only delays the next distinct one; A WiZ bulb pushes on change only; there is no storm to throttle; `min_interval=` changes what a held wake means and adds a RealSleepClock testing burden for no behavioural gain here; ADR-005 explicitly calls out wiz2mqtt as the app that should *not* set it

## Decision Matrix

| Criterion | Push-driven via triggerable=local + EntityNotifier, no min_interval | Keep the 5-second poll tick as the publication driver | Adopt the trigger and also set min_interval as a storm throttle |
| --- | --- | --- | --- |
| Publication latency after a state change | 5 | 2 | 4 |
| Network / bulb traffic on an idle inventory | 5 | 2 | 5 |
| Simplicity of the publication path | 4 | 5 | 3 |
| Consistency with repo-wide ADR-005 | 5 | 1 | 3 |
| Test burden (no RealSleepClock needed) | 5 | 5 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- A bulb state change reaches its retained MQTT topic within a push round-trip rather than up to a poll interval later
- The heartbeat tick sits at 60 s and is deliberately equal to `_DEFAULT_PUSH_STALENESS_THRESHOLD`, so every idle-bulb tick is also a poll-fallback liveness check
- `triggerable="local"` subscribes no MQTT topic — the push wake stays an internal detail
- cap-10u.14's added `@app.command` and the push trigger share one publication path, so the discovery `command_topic` and the fast state updates stay consistent

### Negative

- Two arming paths (heartbeat + notifier) mean a dropped or misplaced `notify()` call degrades latency silently rather than failing loudly
- Timely publication now depends on the push return path, which requires the ADR-004 host-networking deployment
- Real-bulb push and heartbeat cadence is not covered by the unit/integration suite and is deferred to cap-10u.19

## Amendment (2026-09-12) — Corrective

**Rationale:** Completed cap-10u.19 hardware verification found that pywizlight suppresses unchanged heartbeat states and observed rapid slider bursts, correcting the earlier no-burst premise and the deferred verification reference.

> **Justification for amendment (not supersession):** The event-driven architecture, local trigger, OnChange gate, and heartbeat interval remain implemented and unchanged. The correction records their observed operational behavior and does not require a code or migration change, so supersession is not warranted.

### Revised Decision

Publish `bulb_entity` state on the WiZ push, not on the poll tick. `WizBulbAdapter` is constructed with `Wiz2MqttSettings` and an injected `cosalette.EntityNotifier`; its push callback writes the state cache and then calls `notify(bulb_name)`. `bulb_entity` is registered `triggerable="local"` (no MQTT trigger topic subscribed), `publish=cosalette.OnChange()`, `interval=60.0` as a heartbeat/liveness floor, and without `min_interval=`. pywizlight suppresses unchanged heartbeat states, so once the last observed push is older than 60 seconds the next heartbeat tick polls as the fallback; heartbeat cadence does not affect that freshness result. Rapid slider input can burst, but trigger scheduling coalesces to the latest state rather than publishing every input, preserving low latency without a throttle.

!!! note "Editorial note (2026-09-12)"
    Completed cap-10u.19 verification found that pywizlight suppresses consecutive unchanged heartbeat states before the adapter callback. With no refreshed push timestamp, the next heartbeat tick after the age exceeds 60 seconds performs the polling fallback.

!!! note "Editorial note (2026-09-12)"
    Because unchanged heartbeats are suppressed, their cadence does not affect freshness: polling occurs on the next tick once the recorded push age is greater than 60 seconds.

!!! note "Editorial note (2026-09-12)"
    Rapid dimmer-slider input produced bursts. This corrects the original assumption that WiZ only produces a non-bursty change stream; publication scheduling coalesces the latest state instead of publishing every input, so `min_interval=` is still unnecessary.

!!! note "Editorial note (2026-09-12)"
    This amendment replaces the original cap-10u.19 future verification reference with completed manual verification.

### Additional Positive Consequences

- The fallback remains bounded to one poll on the next eligible 60-second tick after push age exceeds the threshold.
- Bursting slider input retains responsive final-state publication without imposing a fixed throttle.

### Additional Negative Consequences

- Idle bulbs can use the polling fallback even when they continue emitting suppressed heartbeat traffic.
