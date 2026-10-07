---
status: Accepted
date: 2026-10-07
impact: high
tags: [health, mqtt, lifecycle, configuration, packaging]
---

# ADR-011: Native cosalette-health Probe as the Default Docker HEALTHCHECK; Exit Codes Still Heal

## Status

Accepted **Date:** 2026-10-07 | Supersedes ADR-010

## Context

ADR-010 removed the Docker `HEALTHCHECK` from every app for two reasons. First, the probe was the most expensive thing in the container: `<app> health` imported the framework and the app, which cost 1.8 s CPU per probe on amd64 and 11 to 13 s wall time on a Raspberry Pi 4 at `cpus: 0.5` (27 to 30 s during start-up, against a 30 s timeout). Second, nothing in these deployments read the Docker health status. Its 2026-10-07 amendment kept the decision after cosalette 0.11.1 shipped the native probe, because the second reason still held, and added the loop-stall watchdog as a per-app opt-in.

cosalette 0.11.1 ships `cosalette-health` as a native Rust binary in its platform wheels (upstream ADR-087). It reads the health file that the app writes on every heartbeat (`COSALETTE_HEALTH_FILE`, every 60 s) and checks two things: the age of the file against `--max-age` (default 3 x the recorded interval, so 180 s) and the device statuses against `--fail-on` (default `stale`). It does not start Python. All app images are `python:3.14-alpine` and install the musllinux wheels, which carry the binary on amd64, arm64 and armv7. Bead cap-2ya9 measured it at `--cpus 0.5` (script and handover in commit `cee6ef1`, `docs/planning/cap-2ya9-pi-probe-measurement.md`):

| Measurement | amd64 (6 cores) | Raspberry Pi 4 (aarch64) |
| --- | --- | --- |
| Old probe (`airthings2mqtt health`, 0.3.0): CPU per probe | 1.83 s | 5.6 to 6.5 s (production) |
| Native probe in the container: CPU, wall time | 0.5 ms, 0.9 ms | 0.7 ms, 1.4 ms |
| Native probe while a busy loop uses the full CPU quota: wall time | 0.6 ms | 1.4 ms (max 80 ms) |
| stdlib fallback: CPU, wall time (busy) | 77 ms, 312 ms | 256 ms, 1.9 s |
| Docker daemon CPU per real `HEALTHCHECK` probe | 60 to 70 ms | 28.5 ms |
| Container CPU per exec (`runc init`, the same for `true`) | 29 ms | not measured |
| Docker probe duration (median, max) | 120 ms, 290 ms | 69 ms, 192 ms |
| Idle app | 1.0 s/h | 1.95 s/h |

The probe binary is now less than 1 % of the cost of a probe. The rest is the Docker exec machinery, which every `CMD` health check pays, `pgrep` included. At a 60 s interval that is about 4 to 6 s of host CPU per hour, or about 0.1 % of one Pi 4 core and 2 to 3 times the idle app. The old probe cost about 300 s per hour on the same Pi. The Raspberry Pi Zero 2 W, the smallest target host, was not reachable; its cores are about 2 to 3 times slower than a Pi 4 core, which still keeps the cost under 0.5 % of a core. The stdlib fallback is too slow for a Pi at 0.5 CPU and is not acceptable as a default.

With the cost gone, the consumer argument is weaker than ADR-010 stated. `docker ps`, `docker compose ps` and container dashboards show the status on the host without an MQTT client. A health file that stops getting younger also reports a wedged event loop during start-up and shutdown, where the loop-stall watchdog is not armed. `depends_on: condition: service_healthy`, autoheal and monitoring tools can use the status with no new image. The facts that ADR-010 built its healing on are unchanged: plain Docker never restarts an `unhealthy` container, `restart: unless-stopped` acts only on a process exit, and cosalette exits with 1 (watchdog backstop), 3 (unexpected exception), 4 (task-restart budget), 5 (`exit_after_stale`) and 6 (loop stall).

## Decision

Adopt the native `cosalette-health` binary as the default Docker `HEALTHCHECK` in each app image through a staged per-app rollout, with `COSALETTE_HEALTH_FILE` set in each adopting image. It costs about 0.1 % of a Raspberry Pi 4 core and makes container health visible on the host. Until an app adopts it, MQTT (status heartbeat, availability, LWT) remains that app's health signal and its image ships no probe. For adopted apps, MQTT remains primary and healing stays with process exits (1, 3, 4, 5, 6) plus `restart: unless-stopped`, so an `unhealthy` status restarts nothing and the repository ships no autoheal.

The target rules for each app after adoption:

1. **The probe lives in the Dockerfile**, in exec form, and runs only `cosalette-health`. Never `<app> health` (0.5 to 0.9 s CPU with 0.11.1) and never the Python fallback. The image must install the native wheel; a cross-app unit test checks the Dockerfile.
2. **Defaults:** `--interval=60s --timeout=5s --retries=3`. `--start-period` is set per app to the time to the first health-file write on a Raspberry Pi, with margin. `COSALETTE_HEALTH_FILE=/tmp/<app>-health.json`.
3. **`--max-age` keeps its default.** The app writes the file on every heartbeat, not on every poll, so the default of 3 x 60 s fits apps with long poll intervals too.
4. **`--fail-on` is decided per app.** The default `stale` suits an app with one device. An app with several independent devices, where one stale device is normal (a bulb with mains power off, a sensor out of range), passes `--fail-on ""` so the probe checks only the age of the file; per-device state is on MQTT.
5. **Compose files define no `healthcheck:`.** The image is the single source. An operator disables the probe with `healthcheck: {disable: true}` and enables autoheal or an orchestrator on their own.
6. **Carried over from ADR-010 unchanged:** each app decides `exit_after_stale` and `restart_on_stale`, and the loop-stall watchdog (`COSALETTE_LOOP_STALL_TIMEOUT`, set in `compose.yml`) stays a per-app opt-in with a value recorded in the app's docs.

Each app adopts the probe in its epic cap-fjop task, together with its freshness and watchdog decisions. `packages/tests/unit/test_container_health_defaults.py` lists the apps that have adopted it; an app that is not on the list must not have a probe yet. This staged rollout is intentional: until adoption, MQTT remains the health signal and the Dockerfile has neither `HEALTHCHECK` nor `COSALETTE_HEALTH_FILE`.

```dockerfile
# Health: MQTT is the primary signal; the probe only makes it visible on the host.
# An unhealthy status restarts nothing. Exits 1, 3, 4, 5 and 6 heal through
# restart: unless-stopped (docs/adr/ADR-011).
ENV COSALETTE_HEALTH_FILE=/tmp/myapp-health.json
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s --retries=3 \
  CMD ["cosalette-health"]
# An app with several independent devices checks only the file age:
#   CMD ["cosalette-health", "--fail-on", ""]
```

## Decision Drivers

- Cost: the native probe costs 0.7 ms CPU on a Raspberry Pi 4; with the Docker exec machinery a probe every 60 s costs about 0.1 % of one core, against about 9 % for the old probe
- Visibility: `docker ps` and container dashboards show health on the host without an MQTT client
- Recovery must stay automatic and single: only a process exit triggers the restart policy, so the probe must not become a second healing path
- Coverage: a health file that stops getting younger also reports a wedged loop during start-up and shutdown, where the loop-stall watchdog is not armed
- Readiness: `depends_on: service_healthy`, autoheal and monitoring can use the status without a new image
- False alarms: an app with several devices must not report unhealthy because one device is legitimately stale

## Considered Options

### Option 1: Keep ADR-010: no probe

Ship no `HEALTHCHECK` and no health file. MQTT is the only health signal, and operators who want a probe add it in their own deployment.

- *Advantages:* No runtime cost at all; One health interface for every consumer
- *Disadvantages:* `docker ps` shows no health status, so a host operator needs an MQTT client to see a problem; Every orchestrator or monitoring user must build the same probe on their own; The cost argument that justified it is gone

### Option 2: Opt-in probe, documented

Ship no `HEALTHCHECK` in the image, but document a compose snippet that sets `COSALETTE_HEALTH_FILE` and runs `cosalette-health`.

- *Advantages:* No cost for operators who do not want it; Operators who want it copy a tested snippet
- *Disadvantages:* Two deployment shapes to document and test for each app; Most deployments never enable it, so the visibility gain stays small; Per-app `--fail-on` and `--start-period` values live in docs that operators copy and then drift from

### Option 3: Native probe as the default HEALTHCHECK in the image (chosen)

Set `COSALETTE_HEALTH_FILE` and a `HEALTHCHECK` that runs `cosalette-health` in every Dockerfile, with per-app `--start-period` and `--fail-on`. Healing stays with exit codes.

- *Advantages:* Health is visible on every host by default, at about 0.1 % of a Pi 4 core; Reports a wedged loop during start-up and shutdown, which the watchdog does not cover; Orchestrators, autoheal and monitoring work without changes to the image; Per-app probe settings live in one place, the Dockerfile, under test
- *Disadvantages:* Costs about 2 to 3 times the idle app's CPU; An `unhealthy` status restarts nothing, which operators can misread; Each app must decide `--fail-on` and `--start-period`

### Option 4: Default probe plus autoheal

Ship the default probe and also an autoheal container in each compose file, which restarts containers that Docker marks unhealthy.

- *Advantages:* Restarts a loop that is wedged during start-up or shutdown
- *Disadvantages:* Adds a privileged container with access to the Docker socket on every host; Two healing paths (exit codes and autoheal) can restart the same fault twice or loop; A false unhealthy status, such as one stale device, turns into a restart

## Decision Matrix

| Criterion | Keep ADR-010: no probe | Opt-in probe, documented | Native probe as the default HEALTHCHECK in the image | Default probe plus autoheal |
| --- | --- | --- | --- | --- |
| Runtime cost on a Raspberry Pi | 5 | 5 | 4 | 3 |
| Health visible on the host | 1 | 2 | 5 | 5 |
| One healing path, no restart loops | 5 | 5 | 5 | 2 |
| Ready for orchestrators and monitoring | 1 | 3 | 5 | 5 |
| Operational simplicity | 5 | 3 | 4 | 1 |
| Low risk of a false unhealthy status | 5 | 4 | 4 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- `docker ps` shows the health of every app, and a host operator sees a stale or wedged app without an MQTT client
- A wedged event loop, also during start-up or shutdown, shows as `unhealthy` within about 6 minutes (file older than 180 s, then 3 failed probes at 60 s)
- Orchestrators, autoheal and monitoring tools can act on the status without a new image
- Healing is unchanged: exits 1, 3, 4, 5 and 6 plus `restart: unless-stopped`, with no second path that can loop
- Probe settings live in the Dockerfile and a cross-app test guards them

### Negative

- Each app costs about 4 to 6 s more host CPU per hour (about 0.1 % of a Pi 4 core), mostly in the Docker exec machinery
- An `unhealthy` status restarts nothing; the app docs must say so, and they must point to MQTT and the exit codes for recovery
- Each app must decide `--fail-on` and `--start-period`; a wrong value gives a false `unhealthy` status
- The app writes the health file to `/tmp` every 60 s; an operator who runs the container with a read-only root filesystem must mount a tmpfs on `/tmp`
- The Raspberry Pi Zero 2 W cost is estimated from the Pi 4 result, not measured; the maintainer accepted the estimate and planned no measurement
- Operators who copied the 0.3.x `healthcheck:` with `<app> health` into their own compose file must remove it, because it overrides the image's cheap probe with the expensive one

_2026-10-07_
