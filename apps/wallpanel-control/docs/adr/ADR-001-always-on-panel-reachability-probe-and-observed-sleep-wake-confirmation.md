---
status: Proposed
date: 2026-10-12
impact: moderate
tags: [health, devices, mqtt, scheduling, lifecycle]
---

# ADR-001: Always-on panel reachability probe and observed sleep/wake confirmation

## Status

Proposed **Date:** 2026-10-12

## Context

wallpanel-control is command-only. `display/state` and `system/action/state` are published only as the answer to a command (plus the `LastAnswers` restore at startup, monorepo ADR-009 amendment of 2026-09-19), and `docs/configuration.md` > "Health and recovery" records that the app polls nothing on a timer. Monorepo ADR-005 records the matching verdict for this app: "No adoption, command-only, nothing polls, so there is nothing to wake".

The early-adopter smoke test of 0.3.11 (epic cap-k0pa, findings F4, F5 and F6, 2026-10-11) showed what this costs a consumer:

- **F4:** while the panel is suspended or hibernated, the retained `display/state` keeps its last value (for example `available:true, state:on`). The only sleep indicator is a command that answers `available:false` after the 5 s SSH timeout. `wallpanel-control/status` stays `online` with `devices.*.status: ok`, which is correct: a sleeping panel is a normal state, not an app fault.
- **F5:** `accepted:true` for `suspend`/`hibernate` arrives about 30 s before the panel sleeps, because logind waits for gnome-shell's delay inhibitor (`InhibitDelayMaxSec`, default 30 s). Hibernate command to ping failing: about 40 s.
- **F6:** `accepted:true` for `wake` means only that the WoL packet was sent. Measured wake: about 18 s from suspend and about 42 s from hibernate. On a Docker bridge network the packet never reached the LAN and nothing reported a failure (the shipped `compose.yml` now uses `network_mode: host`, cap-k0pa.9).

The epic accepted an app-level probe (cap-k0pa.6) and sleep/wake confirmation built on it (cap-k0pa.7), and rejected a framework-level "device degraded" entry in `status.devices`: status reports app health. On 2026-10-12 the user decided that the probe is on by default.

Relevant facts from the code (wallpanel-control 0.3.x, cosalette 0.11.4):

- `SshWallpanel.is_reachable()` returns `True` for any cached connection that asyncssh has not closed, without sending anything. The keepalive from PR #392 (15 s x 3) closes a dead connection only after up to 45 s, so `is_reachable()` alone reports a sleeping panel as reachable for that long.
- `@app.periodic` (ADR-041) has no MQTT presence and is not in `status.devices`, but it gets no `DeviceContext` and no `@app.state` objects, so it cannot publish `display/state`. A lifespan hook gets an `AppContext` without MQTT. The only framework mechanism with a publish channel is a device. Every device, root or named, is announced into the heartbeat (`_wiring/_infra.py::publish_device_availability`); `restore_answers` already appears there today. A root device publishes to `{prefix}/<channel>` and owns no availability source unless it opts in with `unavailable_on`; root devices derive no `stale_after`.
- A root device may declare `triggerable="local"` and wait on a `DeviceTrigger`; a command handler wakes it through an injected `EntityNotifier` (the ADR-005 pattern), which subscribes no MQTT topic.
- The image already adopted the ADR-011 probe with `cosalette-health --fail-on ""` (`_PROBE_APP_DIRS` lists wallpanel-control), so device statuses never make the container unhealthy. The app sets neither `exit_after_stale` nor `restart_on_stale` and registers no adapter `health_check`.

## Decision

Use an always-on SSH liveness probe, run by a new root device `panel_probe`, that republishes `display/state` only when the observed reachability differs from the current answer, and extend `system/action/state` with an `observed` field that the same probe resolves, because this gives consumers a sleep indicator and a sleep/wake outcome at a cost of one SSH exec per interval, without reporting a sleeping panel as an app fault.

**1. Transport and cost.** `is_reachable()` becomes a real check: with a cached open connection it runs `true` over it (one exec channel, no new TCP connection or authentication); otherwise it connects, bounded by `ssh_timeout` (5 s), and keeps the connection cached for the next command. While the panel is awake one probe costs about one round trip and a fork of `true` on the panel (2 880 per day at the default interval). While it sleeps one probe is a connect attempt (ARP and SYN only) that fails within 5 s. In steady state the probe checks reachability only; the panel is read in full only on the transition back to reachable (user decision, 2026-10-12). A full display read every interval would cost three more SSH commands per cycle, and F4 is about sleep, not about screen changes made on the panel; it may come later as an opt-in setting, outside this ADR. `WALLPANEL_CONTROL_PROBE_ENABLED` defaults to `true` and `WALLPANEL_CONTROL_PROBE_INTERVAL` to 30 s; an operator may disable the probe or change the interval.

**2. Ownership of `display/state`.** The retained topic has one logical value, the current `display/state` entry of `LastAnswers`; the command handler and the probe both write through it. One success counts as reachable. A failure is re-probed after 5 s, and two consecutive failures count as unreachable, so one lost packet does not flap the state. When the panel is unreachable and the current answer is not already `available:false`, the probe publishes `{"available":false,"state":null,"brightness_percent":null}`. When the panel is reachable and the current answer is not `available:true`, the probe runs the existing full read (`_poll_display_state`) and publishes it. In steady state it publishes nothing. The probe snapshots the current answer before it probes and drops its result if a command answered in the meantime, so a command always wins. Probe publications go through `LastAnswers.record`, use `ctx.publish(..., retain=True)` with a `DisplayState`-validated payload, and never touch `{prefix}/display/availability`. Worst case loss detection in steady state: interval + 2 x `ssh_timeout` + 5 s = 45 s.

**Open question.** cap-k0pa.6 asks that `display/state` flips within one interval; with the debounce, loss detection can take up to 15 s longer (45 s against a 30 s interval). Not decided yet: accept the 45 s bound as meeting the intent, or lower the default interval to 20 s (worst case 35 s, 4 320 probes per day).

**3. Startup, LastAnswers and MQTT 5 expiry.** The restore stays. The probe's first cycle runs at startup and always publishes its first observation, so within one cycle the restored `display/state` (the last answer, not a reading) is replaced by a fresh read or by `available:false`. A probe result recorded before `restore_answers` attaches wins over the saved answer, by the existing `LastAnswers` rule. Probe publications are retained topics like any other, so the MQTT client's 8 h refresh keeps them inside the 24 h expiry (ADR-009); the probe does not republish an unchanged state for expiry. A saved `system/action/state` with `observed:"pending"` is restored with `observed:null`, because the confirmation died with the process.

**4. Health and staleness.** Panel reachability never reaches `status.devices`: the probe catches every exception per cycle and logs it, declares no `unavailable_on`, and never marks itself or another device unavailable. The heartbeat gains one entry, `panel_probe: ok`, which reports only whether the probe task runs (a task crash shows `error` and the supervisor restarts it, as for `restore_answers`). No `stale_after` is derived for a root device, so `exit_after_stale` and `restart_on_stale` stay unset. The ADR-011 image probe (`--fail-on ""`, 60 s interval, 180 s health-file age) and the 120 s loop-stall watchdog are unchanged: every probe step is asynchronous and bounded.

**5. Sleep and wake confirmation (cap-k0pa.7).** `system/action/state` gains the field `observed` (name and values are a user decision, 2026-10-12): `"pending"`, `"confirmed"`, `"timeout"`, or `null` when nothing is tracked (`accepted:false`, or the probe disabled). An accepted action publishes the acknowledgement with `observed:"pending"` and wakes the probe through `EntityNotifier`. Until the target is observed or `WALLPANEL_CONTROL_ACTION_CONFIRM_TIMEOUT` (default 90 s) runs out, the probe runs every 5 s. Target for `wake`: one successful probe. Target for `suspend`/`hibernate`: two consecutive failures. The probe then republishes the acknowledgement with `confirmed` or `timeout`, and publishes `display/state` as in point 2. A newer action replaces the pending one; the probe republishes an outcome only while its acknowledgement is still the current answer. A `timeout` logs one WARNING; for `wake` it names the usual causes (no host networking, wrong `WOL_BROADCAST`, WoL disabled on the panel NIC), which makes the silent bridge-network failure of F6 visible. Sleep and wake share this one window (user decision, 2026-10-12) rather than separate settings: one setting is simpler, and the 90 s default covers the slowest measured case (hibernate, about 40 s to sleep and about 42 s to wake, plus the 5 s cadence and two `ssh_timeout`s) with about 1.5x margin and still reports a failed wake within 1.5 minutes. A `timeout` is not published on `system/action/error` (user decision, 2026-10-12): the command was accepted, so it is not a command error; consumers read `observed:"timeout"`, and the WARNING log stays.

```jsonc
// system/action/state, retained: acknowledgement, then the observed outcome
{"accepted": true, "action": "wake", "observed": "pending"}
{"accepted": true, "action": "wake", "observed": "confirmed"}
{"accepted": true, "action": "wake", "observed": "timeout"}
{"accepted": false, "action": "suspend", "observed": null}

// display/state, retained: published by the probe only on a transition
{"available": false, "state": null, "brightness_percent": null}
{"available": true, "state": "on", "brightness_percent": 80}
```

## Decision Drivers

- A consumer such as openHAB or Home Assistant must see within about a minute that the panel sleeps or is back, without sending a command (F4)
- accepted means requested; a consumer needs a separate, observed outcome for sleep and wake, and a wake that silently fails must be reported (F5, F6)
- A sleeping panel is a normal state: it must not degrade app health, spend a restart budget or make the container unhealthy
- wake must keep working while the panel sleeps, so nothing may mark the system action unavailable
- The probe is on by default (user decision, 2026-10-12), so its cost on the panel and in logs must be negligible
- The command handler and the probe share one retained topic and must not race or flap

## Considered Options

### Option 1: SSH liveness probe, default on (chosen)

A root device `panel_probe` checks liveness over the cached SSH connection every 30 s, publishes `display/state` only on a debounced reachability transition, and resolves an `observed` field on `system/action/state` after each accepted action.

- *Advantages:* Consumers see sleep and wake through the retained topics they already read; Reuses the cached connection: no new TCP connection, no authentication and no sshd log line per probe, and the first command after a wake no longer pays a dead-connection timeout; Panel reachability stays out of app health; the only heartbeat change is one task-liveness entry; One topic and one additive field; consumers that ignore `observed` are unaffected
- *Disadvantages:* Reverses the documented command-only design and the ADR-005 verdict for this app; Adds a heartbeat entry `panel_probe` that an operator could misread as panel status; `ctx.publish` skips `state_model` validation, so the probe validates its payloads itself

### Option 2: Poll nothing

Keep the command-only design and document that `available:false` in a command answer is the only sleep indicator (the cap-k0pa.2 docs already say so).

- *Advantages:* No code, no load on the panel; No change to the documented design
- *Disadvantages:* The retained `display/state` stays wrong for the whole time the panel sleeps; A failed wake is never reported; a consumer must run its own ping sensor

### Option 3: Probe off by default

The same probe, but opt-in through a setting.

- *Advantages:* Existing deployments see no new traffic or heartbeat entry until they opt in
- *Disadvantages:* Contradicts the user decision of 2026-10-12; Most operators never find the setting, so the F4 and F6 gaps stay open in practice

### Option 4: Reachability in status.devices

Report a sleeping panel in the heartbeat, through an adapter `health_check` or a framework "degraded" device status.

- *Advantages:* Uses a framework signal that tools already read
- *Disadvantages:* status reports app health; the epic rejected this because a sleeping panel is normal; An adapter health check marks both devices offline and spends the restart budget exactly when `wake` must work; Needs an upstream change for a degraded-but-healthy status

### Option 5: Raw TCP connect probe

Open and close a TCP connection to the SSH port each interval, independent of the cached SSH connection.

- *Advantages:* Independent of asyncssh and of the cached connection; Cheaper on the client side than an SSH exec
- *Disadvantages:* sshd logs a pre-authentication disconnect per probe, about 2 880 journal lines per day on the panel; Proves only that the port answers, not that commands work; Does not warm or verify the cached connection, so the next command can still hit a dead one

### Option 6: Outcome on a separate topic

Keep `system/action/state` as the pure acknowledgement and publish the observed outcome on a new retained topic such as `system/action/observed` (framework-opportunities.md item 2).

- *Advantages:* Clean split of acknowledged and observed state
- *Disadvantages:* A consumer must correlate two retained topics to know which action an outcome belongs to; Adds a channel to the AsyncAPI document, the restore set and the ACL output for no information the extra field cannot carry

## Decision Matrix

| Criterion | SSH liveness probe, default on | Poll nothing | Probe off by default | Reachability in status.devices | Raw TCP connect probe | Outcome on a separate topic |
| --- | --- | --- | --- | --- | --- | --- |
| Consumer sees sleep, wake and failed wake | 5 | 1 | 3 | 3 | 4 | 4 |
| App health unaffected by a sleeping panel | 4 | 5 | 4 | 1 | 4 | 4 |
| Cost and log noise on the panel | 4 | 5 | 5 | 4 | 2 | 4 |
| Contract simplicity for consumers | 5 | 4 | 4 | 2 | 5 | 3 |
| Matches the user decision (default on) | 5 | 1 | 1 | 3 | 5 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The retained `display/state` follows the panel within about 45 s of sleep and 30 s of return in steady state, so Home Assistant's light shows off while the panel sleeps (its template maps `state: null` to off)
- After a restart `display/state` is a fresh reading within one probe cycle, which removes the ADR-009 caveat that the restored answer is not a reading
- A wake that does not complete within 90 s is reported as `observed:"timeout"` with a WARNING, which surfaces WoL failures such as the bridge network of F6
- The first command after a wake finds a live, already authenticated connection instead of paying a dead-connection timeout

### Negative

- The app now sends traffic to the panel every 30 s by default. A panel NIC whose WoL mode includes unicast or ARP (`ethtool wol u` or `a`) may be woken by probe traffic; the docs must require magic-packet-only WoL (`wol g`)
- Panel state changed on the panel itself (screen blanked by GNOME, brightness set by hand) is still not seen while the panel stays reachable; the probe reads the display only on a transition. A periodic full read is left to a possible later opt-in setting
- `observed:"confirmed"` means the target was seen once: a `wake` sent during the GNOME inhibitor window is confirmed because the panel still answers, and the panel then sleeps
- The heartbeat gains a `panel_probe` entry, and the restore and probe devices publish through `ctx.publish`, which skips `state_model` validation
- PR 3 (cap-k0pa.6 and .7) must update `docs/configuration.md` ("Health and recovery", new settings `PROBE_ENABLED`, `PROBE_INTERVAL`, `ACTION_CONFIRM_TIMEOUT`), `docs/mqtt-topics.md` (the "No periodic telemetry" note, the `observed` field, the unavailable behaviour), the `main.py`, `display.py` and `restore.py` docstrings, `docs/planning/framework-opportunities.md` item 2, the generated `docs/schema.yaml`, and amend monorepo ADR-005 (wallpanel-control verdict) and ADR-009 (wallpanel-control paragraph) with the adr-create skill

_2026-10-12_
