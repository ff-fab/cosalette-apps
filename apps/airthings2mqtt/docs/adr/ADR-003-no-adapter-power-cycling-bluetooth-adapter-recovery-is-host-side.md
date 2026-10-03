---
status: Accepted
date: 2026-10-02
impact: moderate
tags: [health, lifecycle, devices, security]
---

# ADR-003: No adapter power-cycling; Bluetooth adapter recovery is host-side

## Status

Accepted **Date:** 2026-10-02

## Context

An early adopter lost radon data for 11 to 38 hours in three outages on two hosts (2026-09-24 to 2026-10-02). In one of them the sensor stopped answering and a manual adapter power cycle did not help. The deliberation lives in `docs/TODO/T1-airthings2mqtt-adapter-recovery.md` (gate `cap-oxdp.7`).

Two gaps remained after the error classification fix:

1. **The restart configuration was dead.** `App(restart_after_failures=5, max_restarts=3)` never acted: cosalette restarts an adapter only when it is an async context manager or (from cosalette 0.11.0, ADR-084 upstream) offers `reset()`, and `BleakAirthingsReader` has neither. cosalette logged `health-checkable but not restartable` at every start.
2. **The health check cannot see the incidents.** `health_check()` asks BlueZ whether `hci0` is `Powered`. That stayed true through every outage.

The only app-side escalation that could act on the radio itself is writing `org.bluez.Adapter1.Powered` over the system D-Bus. The container runs as a non-root UID with the system bus socket mounted `:ro`. Neither restricts D-Bus methods: a read-only mount protects the socket path, not the messages sent through it, and the host's D-Bus/BlueZ policy alone decides whether a property write from that identity is allowed. That policy has not been verified for the deployment (`cap-oxdp.13`).

## Decision

airthings2mqtt never changes the Bluetooth adapter's power state (`org.bluez.Adapter1.Powered`) and never resets the radio. Inside the app, recovery is reconnect and backoff only: retry the poll, then mark the entity `offline`. `BleakAirthingsReader` declares `restartable = False`, the dead `restart_after_failures`/`max_restarts` knobs are removed from `main.py`, and `health_check()` stays a read-only `Powered` probe that only feeds availability. Recovering the adapter is the job of the host and the operator.

This is an application invariant (the app does not request power changes), not an authorization guarantee. The desired deployment policy is that host D-Bus/BlueZ policy denies adapter power changes from the container's non-root identity; until `cap-oxdp.13` verifies it, no document may claim that container code cannot power-cycle the adapter.

A future cosalette data-driven restart (`App(restart_on_stale=True)` with an adapter `reset()`) stays acceptable only if it recreates the app's adapter object and never touches the radio; adopting it supersedes the `restartable = False` part of this ADR.

```python
class BleakAirthingsReader:
    restartable = False  # ADR-003: recovery is reconnect/backoff; the radio is host-side

    async def health_check(self) -> bool:
        ...  # read-only Properties.Get(Adapter1, Powered); never Set
```

## Decision Drivers

- A manual adapter power cycle did not help in the reported incident, so an automated one is unproven as a fix.
- Toggling the shared adapter disturbs every other BLE user on the host.
- A Powered write from a non-root container needs a D-Bus policy grant, widening what the container may do on the host.
- Configuration must say what the app actually does; restart knobs that never act mislead operators.
- Host-side tooling (systemd, btmgmt, operator runbook) already owns the adapter's lifecycle.

## Considered Options

### Option 1: A. Declare not restartable, drop restart knobs (chosen)

Set `restartable = False` on `BleakAirthingsReader`, remove `restart_after_failures`/`max_restarts` from `App(...)`, keep `health_check()` read-only. In-app recovery is reconnect/backoff; adapter recovery is host-side.

- *Advantages:* Honest configuration: no knob claims behaviour that never happens; No D-Bus writes, so no policy grant is needed and other BLE users are unaffected; No new code paths to test
- *Disadvantages:* A wedged radio stays wedged until the host or operator acts; Relies on consumers and operators watching availability and staleness

### Option 2: B. Opt-in Powered toggle

After N device-not-found errors with zero advertisers seen, write `org.bluez.Adapter1.Powered=false/true` over D-Bus, behind an opt-in setting.

- *Advantages:* Cheap first escalation the process could perform by itself
- *Disadvantages:* Did not help in the incident it targets; Disturbs every other BLE user on the host; Needs a D-Bus policy that allows the write from a non-root UID

### Option 3: C. Upstream data-driven restart of the adapter object

Use cosalette `restart_on_stale` with an adapter `reset()` so a stale entity recreates the app's adapter object (never the radio).

- *Advantages:* One framework mechanism shared by all apps; No app-specific D-Bus writes
- *Disadvantages:* Recreating a stateless per-poll reader adds nothing the next poll does not already do; Adds restart bookkeeping without a demonstrated failure it fixes

## Decision Matrix

| Criterion | A. Declare not restartable, drop restart knobs | B. Opt-in Powered toggle | C. Upstream data-driven restart of the adapter object |
| --- | --- | --- | --- |
| Effect on the observed incidents | 3 | 1 | 3 |
| Host privilege required | 5 | 1 | 5 |
| Impact on other BLE users | 5 | 1 | 5 |
| Implementation and test cost | 5 | 2 | 3 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The app's configuration matches its behaviour; cosalette 0.11.0 logs the opt-out at INFO instead of a startup WARNING.
- The container needs no D-Bus write permission and never disturbs other BLE users.
- Recovery responsibility is explicit: reconnect/backoff in the app, adapter recovery on the host (runbook `cap-oxdp.11`).

### Negative

- A wedged adapter keeps the entity `offline` until the host or operator recovers it.
- Whether the host actually denies Powered writes from the container identity stays unverified until `cap-oxdp.13`.

_2026-10-02_
