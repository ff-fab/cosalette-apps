---
status: Accepted
date: 2026-09-03
impact: moderate
tags: [architecture, mqtt, telemetry, lifecycle, devices]
---

# ADR-005: Event-Driven Publication Adoption

## Status

Accepted **Date:** 2026-09-03

## Context

Until cosalette 0.8.0 every app in this monorepo published telemetry on a scheduler tick and nothing else. An adapter that *knew* a value had changed — a WiZ bulb's UDP push, a JeeLink frame off the serial stream, a Vitotronic parameter just written over Optolink — had no way to say so. The push callback wrote a cache and returned; the fresh payload then sat until the next tick fired. Apps compensated in three separate ways, all of them workarounds: wiz2mqtt ran a 5-second poll tick purely to shorten push-to-publish latency; jeelink2mqtt maintained a hand-rolled freshness ledger (`SharedState.last_reading_at` vs `last_published_reading_at`) plus the interleaving race that ledger existed to close; vito2mqtt documented the latency away as *"Eventual Consistency"* in `devices/commands.py`, accepting that a write to the `system` group takes up to `polling_system` = 3600 s to appear in the retained state topic.

0.6.3 also blocked the obvious fix structurally: `triggerable=` and `group=` were mutually exclusive, so the very apps that most needed a wake (vito2mqtt's seven `group="optolink"` telemetry groups, serialised for bus exclusion) were the ones forbidden from declaring one. `triggerable=` itself meant only *"subscribe an MQTT trigger topic"*, so the sole way to arm an entity was to expose a public topic to the broker — an unacceptable answer for an in-process push.

cosalette 0.8.0 (upstream ADR-064 through ADR-067) closes all of it: `triggerable=` widens from `bool` to a trigger-source declaration, an injectable `EntityNotifier` arms the *same* trigger slot the MQTT path arms, `@app.device` gains a `DeviceTrigger`, `min_interval=` bounds trigger-initiated runs, and the `group=` exclusion is gone — a woken group member simply joins the group's next batch, preserving bus exclusion. All ten pin declarations moved from `>=0.6.3,<0.7` to `>=0.8.0,<0.9` in one commit, so the API is available repo-wide with no further version work. This ADR records the repo-wide adoption decision on the evidence of the four apps that have now adopted it, exactly as ADR-004 did for runtime HA discovery.

## Decision

Use cosalette 0.8.0 event-driven publication — `triggerable="local"`/`"both"` plus an injected `EntityNotifier`, or `@app.device(triggerable="local")` plus a `DeviceTrigger` — for every app whose adapter has a real event to publish on, and treat `interval=` in those apps as a heartbeat rather than the publication driver. Apps with no event source stay purely scheduled; the pattern is opt-in per entity, never a blanket migration.

Per-app verdicts, all four adoptions now implemented:

| App | Verdict | Shape |
| --- | --- | --- |
| wiz2mqtt | Adopted — `cap-10u.21`, `76950cc` | `triggerable="local"` on `bulb_entity`; adapter takes `EntityNotifier`, wakes from the UDP push callback; tick 5 s → 60 s as heartbeat/liveness probe |
| vito2mqtt | Adopted — `cap-rdj`, `552f515` | `triggerable="local"` + `min_interval=15.0` on all seven `group="optolink"` telemetry groups; command handlers take `EntityNotifier` and arm their own group after a successful write |
| jeelink2mqtt | Adopted — `cap-d4j`, `72939ec` | `@app.device(triggerable="local")` + `DeviceTrigger`; stream receiver arms the sensor after caching a calibrated reading; deletes the freshness ledger outright |
| airthings2mqtt | Adopted — `cap-mpd`, `f7a78b4` | already `triggerable=True` on a public `/set` topic; gains `min_interval=30.0` only |
| caldates2mqtt | Adopted — `cap-mpd`, `f7a78b4` | already `triggerable=True` on a public `/set` topic; gains `min_interval=60.0` only |
| gas2mqtt | No adoption | I²C magnetometer is polled, no interrupt line in the port; counter already polls at ~1 s and publishes its own state |
| velux2mqtt | No adoption | expanded `@app.device` cover publishes from its own loop; calibration already uses `asyncio.wait_for` on its own queue — `DeviceTrigger` would be a lateral move |
| wallpanel-control | No adoption | command-only; `display.py` publishes synchronously after each accepted command. Nothing polls, so there is nothing to wake |
| suncast | No adoption | one root telemetry entity computing solar geometry from a clock. The sun does not push |

Adoption rules. Use `triggerable="local"` — the bare string literal — when the only arming path is in-process; it subscribes **no** MQTT topic, so it adds no public surface. Reserve `"both"` for an entity that genuinely wants operator-initiated refresh as well, and `True`/`"mqtt"` keeps its existing meaning unchanged. Inject `EntityNotifier` by annotation into the adapter or handler that owns the event, and call `notify(name)` *after* the cache write, never before. Set `min_interval=` wherever a wake costs a real round-trip on a shared or remote resource; deliberately do **not** set it where `publish=OnChange()` already gates duplicates (wiz2mqtt), nor on a `DeviceTrigger` whose `wait()` return value is read as *"nothing arrived"* (jeelink2mqtt) — with a throttle set, a `"scheduled"` return no longer carries that meaning.

```python
# telemetry: local-only wake, throttled (vito2mqtt)
app.add_telemetry(
    name=group,
    interval=poll_interval,          # heartbeat, not the driver
    group="optolink",                # bus exclusion preserved
    triggerable="local",             # string literal; no MQTT topic subscribed
    min_interval=15.0,               # bounds trigger-initiated runs only
)

# the event side: inject the notifier, arm after the write
async def handler(..., notify: cosalette.EntityNotifier) -> None:
    if writes:
        await port.write(writes)
        notify(group)                # accelerates the next refresh

# devices: DeviceTrigger instead of a notifier (jeelink2mqtt)
@app.device(name=..., triggerable="local", state_model=SensorStateModel)
async def sensor_entity(ctx, config, settings, state, trigger: cosalette.DeviceTrigger):
    reason = await trigger.wait(timeout=1.0)
```

## Decision Drivers

- Publish when the device says the value changed, not up to a full poll interval later — vito2mqtt's `system` group went from a 3600 s worst case to seconds
- Stop paying for latency with poll frequency: wiz2mqtt's 5 s tick existed only to shorten push-to-publish delay and could drop to a 60 s heartbeat once the push itself published
- Delete hand-rolled freshness bookkeeping and the races it exists to close — the framework's arm coalesces, so jeelink2mqtt's published-reading timestamp comparison disappeared entirely
- Keep the wake in-process: `triggerable="local"` adds no public MQTT topic, so an internal implementation detail does not become a broker-visible control surface
- Bound the cost of a wake on shared or remote resources — a 4800-baud serial bus, a BLE connect to a battery sensor, a CalDAV fetch against someone else's server
- Adopt only where an event actually exists; four apps have no event source and gain nothing from the pattern

## Considered Options

### Option 1: Status quo — scheduler-driven publication with per-app workarounds

Keep publishing on the tick only. Apps that need lower latency keep shortening their poll interval (wiz2mqtt's 5 s), keep their own freshness ledgers (jeelink2mqtt's `last_reading_at` / `last_published_reading_at`), or keep documenting the latency as an accepted consistency property (vito2mqtt's "Eventual Consistency" note).

- *Advantages:* Zero code change and zero new framework surface — the pin bump alone would have sufficed; One publication path per app, trivially predictable: everything happens on the tick; No new failure mode from an arm that is dropped, coalesced, or held inside a throttle window
- *Disadvantages:* vito2mqtt keeps a documented 3600 s worst case between writing a system parameter and seeing it in the retained state topic; Latency is bought with poll frequency, which is exactly the wrong currency on a 4800-baud serial bus or a battery-powered BLE sensor; Each app reinvents freshness bookkeeping, and jeelink2mqtt's version carried a real interleaving race; The push callback stays publication's dead end: the adapter knows the value changed and has no way to say so

### Option 2: Adopt event-driven publication repo-wide where an event exists (chosen)

Every app whose adapter has a real event declares it: `triggerable="local"` plus an injected `EntityNotifier` for telemetry, `@app.device(triggerable="local")` plus a `DeviceTrigger` for devices, `min_interval=` wherever a wake costs a round-trip. `interval=` is redefined as a heartbeat. Apps with no event source are explicitly excluded rather than left ambiguous.

- *Advantages:* A push, a frame, or a completed write publishes through the identical handler, `OnChange()` gate and availability debounce a scheduled tick uses — one publication path, two arming paths; Poll intervals can rise rather than fall: wiz2mqtt's tick went 5 s → 60 s and became a liveness probe deliberately equal to the push-staleness threshold; Framework-owned arm coalescing deletes app-level freshness ledgers and their races outright; `triggerable="local"` keeps the wake in-process — no MQTT topic is subscribed, so no internal detail leaks to the broker; `min_interval=` holds an arm pending inside a closed window rather than dropping it, so an on-demand refresh still happens once the window reopens; Bus exclusion survives: a woken `group=` member joins the group's own next batch instead of getting its own out-of-band read
- *Disadvantages:* Two arming paths per adopting entity, so a missing or misplaced `notify()` call is a silent latency regression rather than a loud failure; `min_interval=` changes what a `DeviceTrigger.wait()` `"scheduled"` return means, so it cannot be applied uniformly — jeelink2mqtt and wiz2mqtt must deliberately omit it; Adoption changed vito2mqtt's documented consistency model, forcing an amendment to its app-local ADR-007; `min_interval=` values (15 s / 30 s / 60 s) are hard-coded per app rather than configurable per deployment; Timing assertions around the throttle needed a `RealSleepClock` because `FakeClock` advances virtual time instantly — now duplicated in three apps

### Option 3: Adopt only for genuine external push sources

Restrict adoption to adapters receiving an unsolicited inbound event — wiz2mqtt's UDP push and jeelink2mqtt's serial frames. vito2mqtt keeps polling (its wake follows our own command, not an external event), and the `min_interval=` throttle is skipped everywhere as a separate concern.

- *Advantages:* Smallest blast radius: two apps change, and only where a device genuinely pushes; Avoids amending vito2mqtt's ADR-007 and its documented eventual-consistency model; Sidesteps the `min_interval=` interaction with `DeviceTrigger.wait()` return semantics entirely
- *Disadvantages:* Leaves the worst latency in the repo untouched — vito2mqtt's 3600 s system-group case is the single largest win available; Ignores that ADR-067 was written precisely to unblock coalescing-group members like vito2mqtt's; Leaves airthings2mqtt's and caldates2mqtt's public `/set` topics unbounded, so any broker client can drive back-to-back BLE connects or CalDAV fetches; Draws the line at "is the event external" rather than "does an event exist", which is not a property that predicts anything useful about publication latency

## Decision Matrix

| Criterion | Status quo — scheduler-driven publication with per-app workarounds | Adopt event-driven publication repo-wide where an event exists | Adopt only for genuine external push sources |
| --- | --- | --- | --- |
| Publication latency after a known state change | 1 | 5 | 3 |
| Cost paid on the constrained resource (serial bus, BLE, remote server) | 2 | 5 | 3 |
| App-level bookkeeping and race surface eliminated | 1 | 5 | 4 |
| Predictability of the publication path (5 = one path, no hidden arming) | 5 | 3 | 4 |
| Uniformity of the rule across the nine apps | 4 | 4 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- vito2mqtt's worst-case write-to-visible latency drops from `polling_system` = 3600 s to seconds, and the 300 s `outdoor`/`burner` groups improve correspondingly — without loosening Optolink bus exclusion, because the woken member joins the group's own next batch
- wiz2mqtt's poll tick rose 5 s → 60 s: publication no longer depends on it, and 60 s deliberately equals the adapter's push-staleness threshold so every idle-bulb tick doubles as a liveness probe
- jeelink2mqtt deleted `SharedState.last_reading_at` and `last_published_reading_at` along with the interleaving race they closed — the framework's arm coalescing subsumes both
- A wake publishes through the identical handler, `OnChange()` gate and availability debounce as a scheduled tick, so there is one publication path with two arming paths rather than two publication paths
- `triggerable="local"` subscribes no MQTT topic, so the in-process wake adds no broker-visible control surface — an internal detail stays internal
- airthings2mqtt's and caldates2mqtt's public `/set` topics are now bounded (30 s / 60 s) against a client driving back-to-back BLE connects or CalDAV fetches, and a wake inside a closed window is held rather than dropped, so an on-demand refresh still happens
- Four apps (gas2mqtt, velux2mqtt, wallpanel-control, suncast) are explicitly recorded as needing no adoption, each for a stated reason, so the question does not get re-litigated per release

### Negative

- **The vito2mqtt wake accelerates the next refresh; it does not confirm the value just written.** A group's command signals and its telemetry signals are disjoint addresses by design, so the re-read picks up the boiler's *reaction*, not an echo of the written parameter. ADR-007's eventual-consistency model is amended, not repealed — the window shrinks from up to an hour to seconds, and that is the whole of the claim
- Every adopting entity has two arming paths, so a `notify()` call that is missing, or placed before the cache write instead of after, degrades silently into the old scheduled behaviour rather than failing loudly
- `min_interval=` cannot be applied uniformly: with a throttle set, a `DeviceTrigger.wait()` return of `"scheduled"` no longer means "no reading arrived", so jeelink2mqtt must omit it, and wiz2mqtt omits it because `publish=OnChange()` already gates duplicates. The rule is per-entity judgement, not a default
- `min_interval=` values are hard-coded constants (15 s vito2mqtt, 30 s airthings2mqtt, 60 s caldates2mqtt) with no per-deployment configuration; a slower bus or a stricter CalDAV server needs a code change
- `FakeClock` advances virtual time instantly and so erases the very window a throttle test measures. Three apps now carry a duplicate `RealSleepClock` in their integration harnesses — an upstream or shared-fixture home for it is outstanding
- wiz2mqtt has no user-facing documentation (`docs/index.md` links to `getting-started.md`, `configuration.md` and `mqtt-topics.md`, none of which exist), so its push-driven publication behaviour is documented only in ADRs and commit messages
- `interval=` now means different things in adopting and non-adopting apps — heartbeat in the former, publication driver in the latter — which readers of a composition root must hold in mind

_2026-09-03_
