---
status: Accepted
date: 2026-09-06
impact: moderate
tags: [configuration, architecture, naming, devices]
---

# ADR-002: IP Address as Bulb Identity

## Status

Accepted **Date:** 2026-09-06

## Context

Every command wiz2mqtt sends and every state read it performs is addressed to a bulb by literal IPv4 address: `port.set_state(config.ip, ...)`, `_last_push_at[ip]`, the push callback keyed by `ip`. pywizlight's `wizlight(ip)` constructor takes an address, and its push subscription (`start_push`) registers a callback per address. WiZ bulbs also expose a MAC and can be found by UDP broadcast discovery.

The legacy `wizcontrol.py` hard-coded a Python dict of names to lists of `wizlight("192.168.12.x")` — addresses inline in the source, no MAC anywhere. In practice these bulbs sit on static DHCP reservations, so their addresses do not move.

The open question for the rewrite was what a `[[bulbs]]` entry is keyed by: the IP as the identity, the MAC as the identity with a discovery step to resolve it to an address, or a full discovery-and-track model where wiz2mqtt keeps a live MAC→IP map and follows a bulb across address changes.

## Decision

Use the literal IPv4 address as a bulb's identity: `[[bulbs]]` requires `name` and `ip`, and `ip` is what every adapter call is addressed to. `mac` stays an optional bare-hex field used only for a one-time startup verification that the configured address still belongs to the intended bulb — it is never resolved, tracked, or used for addressing. Operators are expected to give WiZ bulbs static DHCP reservations.

```python
[[bulbs]]
name = "desk"
ip = "10.0.0.10"

[[bulbs]]
name = "lamp"
ip = "10.0.0.11"
mac = "a8bb5006033d"   # optional: verified once at startup, never used to address
```

## Decision Drivers

- pywizlight addresses bulbs by IP for both commands and the push subscription — the SDK has no MAC-addressed mode
- WiZ bulbs are effectively fixed-address devices in a real deployment: static DHCP reservations are standard practice and the legacy app depended on it for years
- A MAC→IP tracking layer needs periodic broadcast discovery, a mutable map, and a policy for 'MAC seen at a new address' — real complexity for a failure mode a DHCP reservation already removes
- Identity must be stable across restarts and match the MQTT topic segment, which the operator-chosen `name` already provides — the address is just the transport handle
- A wrong address should fail loudly and early, not silently control someone else's bulb

## Considered Options

### Option 1: IP is the identity, MAC verifies once (chosen)

`ip` is mandatory and is the address for every call. `mac`, if given, is checked once at startup against what the bulb at that address reports; a mismatch is a startup error. No discovery, no tracking.

- *Advantages:* Maps one-to-one onto pywizlight's addressing model with no adapter-side indirection; Deterministic: the same config produces the same behaviour on every start; Optional MAC check catches the common misconfiguration (address reused by another bulb) at startup rather than in production; No background discovery traffic on the LAN
- *Disadvantages:* A bulb whose address changes (no reservation, DHCP lease churn) goes unavailable until the config is edited; Relies on an operator practice (static reservations) that the app cannot enforce

### Option 2: MAC is the identity, resolved via discovery at startup

`[[bulbs]]` is keyed by `mac`. At startup wiz2mqtt runs a UDP broadcast discovery, builds a MAC→IP map, and addresses calls by the resolved IP for the rest of the process lifetime.

- *Advantages:* Config is address-free, so it survives a one-off address change across a restart; MAC is a genuinely stable hardware identifier
- *Disadvantages:* Startup now depends on a broadcast round-trip that pywizlight's discovery can hang on (issue #200) and that a segmented / VLAN'd network may drop entirely; A bulb that is powered off at startup is simply missing — there is no address to fall back to; Adds a discovery code path and its failure handling to the critical startup path for a problem reservations already solve

### Option 3: Full MAC->IP tracking with periodic re-discovery

Key by `mac`, and keep re-running discovery on an interval so wiz2mqtt follows a bulb across address changes at runtime, updating the live map and re-subscribing push callbacks.

- *Advantages:* Tolerates address changes with no operator action at all; Closest to a plug-and-play experience
- *Disadvantages:* A mutable identity map is shared state that every adapter call and the push bookkeeping must consult and stay consistent with; Needs a conflict policy for 'this MAC is now at an address another bulb had', plus re-subscription churn on the push sockets; Continuous broadcast traffic and a moving target for tests, to handle a scenario a DHCP reservation eliminates; pywizlight discovery reliability (hangs, dropped broadcasts) now affects steady-state operation, not just startup

## Decision Matrix

| Criterion | IP is the identity, MAC verifies once | MAC is the identity, resolved via discovery at startup | Full MAC->IP tracking with periodic re-discovery |
| --- | --- | --- | --- |
| Fit with pywizlight's addressing model | 5 | 3 | 2 |
| Determinism and testability | 5 | 3 | 2 |
| Tolerance of an address change | 2 | 3 | 5 |
| Implementation and state complexity | 5 | 3 | 1 |
| Behaviour on a segmented / broadcast-restricted network | 5 | 2 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The adapter passes `config.ip` straight to pywizlight with no identity-resolution layer
- A given `wiz2mqtt.toml` behaves identically on every start; integration tests set `ip` and assert on it directly
- The optional bare-hex `mac` check turns 'the address now points at a different bulb' into a startup failure instead of a silent wrong-bulb command
- No broadcast discovery traffic and no dependency on pywizlight's hang-prone discovery in the daemon's normal operation

### Negative

- A bulb whose IP changes is unavailable until an operator edits `wiz2mqtt.toml` and restarts
- Correct operation depends on static DHCP reservations, which wiz2mqtt documents but cannot enforce
- The planned `discover` CLI subcommand (cap-10u.15) is an onboarding aid that prints `[[bulbs]]` entries; it is explicitly not wired into the daemon's addressing

_2026-09-06_
