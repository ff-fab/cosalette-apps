---
status: Accepted
date: 2026-10-04
impact: moderate
tags: [health, mqtt, lifecycle, configuration]
---

# ADR-010: MQTT Is the Health Signal: No Docker HEALTHCHECK, Supervised Restart via Exit Codes

## Status

Accepted **Date:** 2026-10-04 | Amended **Date:** 2026-10-07

## Context

cosalette 0.11.0 added an opt-in health file (`COSALETTE_HEALTH_FILE`) and a `<app> health` probe for container orchestrators (upstream ADR-083). Its rationale: in the airthings2mqtt outages behind upstream epic cos-4mv5 the process stayed up for 11 to 38 h while every entity was stale, and nothing outside MQTT could see the problem. airthings2mqtt adopted the probe as a Docker `HEALTHCHECK` in PR #323 (bead cap-oxdp.9), and epic cap-fjop planned the same for the other apps. suncast already shipped a `pgrep -f suncast` compose healthcheck.

**The probe is the most expensive thing in the container.** It reads a file of about 300 bytes but imports the whole framework and the app. Measured on amd64 (`--cpus 0.5`, image 0.3.0 without bytecode): 3.6 s wall time and 1.8 s CPU per probe, peak RSS 54 MB. At one probe per minute that is about 107 s of CPU per hour, against about 1 s per hour for the idle app. On two Raspberry Pi 4 hosts at `cpus: 0.5` an idle probe took 11 to 13 s, a start-up probe 27 to 30 s, and two overlapping probes hit the 30 s timeout. Compiling bytecode cuts the CPU by about 70 % but leaves the probe far above the app.

**Nobody reads the result.** No compose file in this repository uses `depends_on: condition: service_healthy`, no autoheal is deployed, and no monitoring reads `docker inspect .State.Health`. Plain Docker never restarts an `unhealthy` container; `restart: unless-stopped` acts only on a process exit. The status is visible only to a human who runs `docker ps`.

**MQTT already carries the signals.** The freshness watchdog (upstream ADR-080) publishes retained `offline` on `{prefix}/{device}/availability` and `stale` in the `{prefix}/status` heartbeat when no fresh cycle arrives within `stale_after`. The last will is `{prefix}/status` = `offline`, retained, QoS 1. aiomqtt drives its 60 s keepalive from the asyncio loop with no network thread, so a dead process fires the LWT at once and a blocked event loop fires it about 90 s later. Home Assistant and other consumers already see these signals.

**Healing is a process exit plus the restart policy.** cosalette exits with code 3 on an unexpected exception, 4 when the task-restart budget is exhausted (`on_task_failure="restart"` is the default, ADR-081) and 5 when `exit_after_stale` expires (ADR-083). Every shipped compose service sets `restart: unless-stopped`. ADR-083 rejected "exit on stale only" because it cannot observe health without killing the process (MQTT covers that) and because it misses a wedged event loop that never reaches the freshness check. That second gap remains: there is no loop-stall watchdog in cosalette today.

## Decision

Use MQTT (status heartbeat, per-device availability and the LWT) as the only health signal, ship no Docker `HEALTHCHECK` or compose `healthcheck` in any app, and heal through a non-zero process exit (codes 3, 4 and 5) plus `restart: unless-stopped`, because the probe costs about 100 times the idle app's CPU and nothing in these deployments consumes Docker health status. Apps do not set `COSALETTE_HEALTH_FILE`; the `health` subcommand stays available for operators who run their own probe. Each app decides `exit_after_stale` and `restart_on_stale` on its own merits; airthings2mqtt sets `exit_after_stale` to 5 h (configurable), which restarts it about 6 h after the last good reading. This changes the direction of epic cap-fjop: its per-app item (2) becomes "no Docker HEALTHCHECK; decide exit_after_stale / restart_on_stale per app".

```yaml
services:
  myapp:
    # Restarts on exit 3 (exception), 4 (task budget) and 5 (exit_after_stale).
    restart: unless-stopped
    # No healthcheck: MQTT carries health (status heartbeat, availability, LWT).
```

## Decision Drivers

- Cost: the ADR-083 probe imports the framework and the app every minute, about 1.8 s CPU per probe on amd64 and 11 to 13 s wall time on a Raspberry Pi 4 at 0.5 CPU
- No consumer: nothing in these deployments reads Docker health status, and plain Docker does not restart unhealthy containers
- Existing coverage: the freshness watchdog, heartbeat and LWT already report stale data, a dead process and a blocked event loop over MQTT
- Recovery must be automatic: only a process exit triggers the restart policy, so healing belongs in exit codes, not in a status flag
- Simplicity: one health interface for every app and consumer instead of two that can disagree

## Considered Options

### Option 1: MQTT as the health signal, supervised restart (chosen)

No HEALTHCHECK in images or compose files. MQTT heartbeat, availability and LWT report health; a non-zero exit (3, 4, 5) plus `restart: unless-stopped` heals. Apps opt into `exit_after_stale` where a restart can plausibly help.

- *Advantages:* Zero runtime cost: no probe process, no health file writes; The signal reaches the consumers that already watch MQTT (Home Assistant, Node-RED, exporters); Healing is real: a stale or crashed app restarts, which an unhealthy flag never did
- *Disadvantages:* A wedged event loop is reported (LWT after about 90 s) but not healed until cosalette ships a loop-stall watchdog; `docker ps` no longer shows a health column for these apps

### Option 2: Keep the ADR-083 probe as Docker HEALTHCHECK

Status quo from PR #323: set `COSALETTE_HEALTH_FILE` in the image and run `<app> health` every 60 s, and roll it out to the other apps as epic cap-fjop planned.

- *Advantages:* Detects a stale health file, so it notices a blocked event loop locally; Follows the upstream recommendation as written today
- *Disadvantages:* Costs about 100 times the idle app's CPU and nearly doubles peak memory during each probe; Start-up and overlapping probes hit the 30 s timeout on a Raspberry Pi; Produces a status nobody reads; Docker does not act on it

### Option 3: Cheap probe (pgrep, stdlib or Rust) as HEALTHCHECK

Keep a HEALTHCHECK but make it cheap: `pgrep` as suncast had, a stdlib-only Python reader of the health file, or a Rust binary shipped in the cosalette wheel.

- *Advantages:* A stdlib or Rust reader costs 0.03 s or less of CPU per probe; Keeps a health column in `docker ps`
- *Disadvantages:* Still produces a status nobody reads, so it heals nothing; `pgrep` only proves the process exists, which the restart policy already handles; The stdlib and Rust readers do not exist upstream yet and need a health-file contract

### Option 4: HEALTHCHECK plus an autoheal watchdog

Keep a probe and deploy autoheal (or similar) that restarts containers Docker marks unhealthy.

- *Advantages:* Restarts a wedged event loop without a framework change
- *Disadvantages:* Adds a privileged container with access to the Docker socket on every host; Keeps the probe cost, and a restart still cannot fix a missing sensor; Duplicates what `exit_after_stale` and a future loop-stall watchdog do in-process

## Decision Matrix

| Criterion | MQTT as the health signal, supervised restart | Keep the ADR-083 probe as Docker HEALTHCHECK | Cheap probe (pgrep, stdlib or Rust) as HEALTHCHECK | HEALTHCHECK plus an autoheal watchdog |
| --- | --- | --- | --- | --- |
| Runtime cost on a Raspberry Pi | 5 | 1 | 4 | 1 |
| Signal reaches existing consumers | 5 | 2 | 2 | 3 |
| Automatic recovery | 4 | 1 | 1 | 4 |
| Operational simplicity | 5 | 3 | 3 | 1 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The largest CPU consumer in the airthings2mqtt container is gone, and start-up no longer competes with probes on a Raspberry Pi
- A sensor that stays stale ends airthings2mqtt with exit code 5 and the restart policy restarts it; before, an unhealthy flag changed nothing
- Every app has one health interface, documented per app in its MQTT topic and troubleshooting pages
- suncast loses a `pgrep` check that only proved the process existed

### Negative

- A wedged event loop is reported over MQTT (LWT `offline` after about 90 s) but not healed until cosalette ships an opt-in loop-stall watchdog; tracked as an upstream bead
- Operators who added their own `healthcheck:` override in compose must remove it, or it keeps running the expensive probe; without `COSALETTE_HEALTH_FILE` the probe now always fails
- Images released before this change (airthings2mqtt 0.3.x) still carry the HEALTHCHECK until upgraded; `healthcheck: disable: true` in compose turns it off in the meantime
- A dead airthings2mqtt sensor causes one harmless restart about every 6 h, visible as LWT `offline` then `online`
- `docker ps` shows no health status for these apps

## Amendment (2026-10-07) — Additive

**Rationale:** cosalette 0.11.1 ships the two upstream pieces this ADR waited for or rejected as missing. The loop-stall watchdog (upstream ADR-088) closes the gap recorded under Negative consequences: a wedged event loop can now end in an exit. A native `cosalette-health` probe (upstream ADR-087) makes a probe cheap (about 1 ms per run). This amendment records how both fit the decision, which itself is unchanged.

### Additional Sub-Decision: Loop-stall watchdog is a per-app opt-in, set in compose

cosalette 0.11.1 adds `COSALETTE_LOOP_STALL_TIMEOUT` (seconds, unset means off). A thread outside the event loop exits the process with code 6 (`EXIT_LOOP_STALL`) when the loop has not run for that long, after writing every thread's stack to stderr. A stall inside C code that holds the GIL is caught by a faulthandler backstop after twice the timeout and exits with code 1. Both codes are restarted by `restart: unless-stopped`. The watchdog is armed only for the run phase, so a hang during startup or shutdown is still not detected. It is an environment variable, not an `App()` parameter, so an app adopts it in its `compose.yml` (and `.env.example` where present) with a value larger than its longest legitimate blocking call, documented in the app's docs. The value is decided per app and tracked in beads; there is no repository-wide default. The healing exit codes of this ADR become 1 (backstop), 3, 4, 5 and 6.

### Additional Sub-Decision: The native probe does not change the decision

Option 3 rejected a cheap probe because nothing reads Docker health status, not only because the readers did not exist. cosalette 0.11.1 ships `cosalette-health` as a native binary in its platform wheels and a stdlib-only script elsewhere, with a versioned health-file contract and exit codes limited to 0 and 1. That removes the cost argument but not the consumer argument, so apps still ship no `HEALTHCHECK` and do not set `COSALETTE_HEALTH_FILE`. An operator who runs an orchestrator that acts on container health can set both in their own deployment and probe with `["CMD", "cosalette-health"]`, not `<app> health`.

### Additional Positive Consequences

- An app that sets `COSALETTE_LOOP_STALL_TIMEOUT` heals a wedged event loop during the run phase through exit code 6 and the restart policy, which closes the gap this ADR recorded

### Additional Negative Consequences

- Apps that do not opt in keep the original gap: a wedged loop is reported by the LWT but not healed
- A watchdog timeout shorter than an app's longest legitimate blocking call restarts the app on every such call, so each value needs a per-app justification
