---
status: Accepted
date: 2026-09-13
impact: high
tags: [mqtt, configuration, devices, telemetry, architecture]
---

# ADR-007: Mains Power Awareness Through Power Sources

## Status

Accepted **Date:** 2026-09-13

## Context

Some WiZ bulbs sit behind smart relays. openHAB or Home Assistant holds a signal that tells whether the circuit has mains power. "Powered" is not the same state as "on". Today wiz2mqtt cannot tell the two apart: an unpowered bulb looks the same as a faulty bulb. Both show `availability = offline`.

The hard case is a mixed environment. The same lights are controlled by wiz2mqtt and by classic wall switches. When a wall switch cuts the circuit, every bulb on it goes dark and unreachable at once. wiz2mqtt then reads each absent bulb on every telemetry cycle. An absent bulb holds the `asyncio.Lock` of pywizlight for the full 13 s timeout. A failed cycle costs 13 s plus the 60 s interval, because the scheduler delays after completion rather than at a fixed rate.

A consumer wants one simple rule. In openHAB the rule "the lamp is lit" must come from one message, not from a join of two topics. The signal is optional: many circuits have no relay, and the feature must still work there.

A lighting group (`[[groups]]`, ADR-003) matches a circuit most of the time, but not always. One bulb of a group can sit on a different circuit. The addressing must handle that exception without a second inventory.

The design was settled in a design interview (decisions Q2, Q4, Q5, Q11, Q14, Q15, Q20, Q21, Q23). This ADR records the addressing, the state model, the traffic rule, the configuration surface and the legacy mapping. ADR-008 records the restore. ADR-009 records the power requests.

## Decision

Add a `[[power_sources]]` block to the inventory. A power source declares a circuit and claims member bulbs. wiz2mqtt derives a **belief** about the power of each source and publishes the belief, not the raw relay signal. The belief goes into the state payload of every member bulb as a `powered` key. A consumer computes "the lamp is lit" as `state AND powered` from one message.

**Source of the `powered` value.** Three options were weighed: (a) republish the raw relay signal; (b) publish a derived belief where evidence outranks the signal; (c) no source-level entity, only a per-bulb flag. Option (b) is chosen. The belief has three values, `on`, `off` and `unknown`, and follows three rules in order:

1. If a minimum of one member bulb answers, the belief is `on`. Evidence outranks the signal.
2. If no bulb answers and a signal exists, the belief is the signal.
3. If no bulb answers and no signal exists, the belief is `unknown`.

Rule 1 makes the `powered` flag useful on a circuit that has no relay signal at all.

**Bulb state while unpowered.** Three options were weighed: (a) publish `OFF`; (b) publish the desired state plus a `powered` key; (c) publish `unknown`. Option (b) is chosen. While wiz2mqtt cannot observe the bulb, `wiz2mqtt/{bulb}/state` publishes the desired state (ADR-008). Option (a), "publish OFF", was proposed first and then withdrawn. The reason: reality is recoverable from intent as `state AND powered`, but intent is not recoverable from reality. The desired state carries strictly more information.

**Addressing.** Three options were weighed: (a) a `power_source` key on every bulb only; (b) a `[[power_sources]]` block with `group` or `members` plus a per-bulb override; (c) reuse `[[groups]]` with extra keys. Option (b) is chosen. The membership resolves per bulb, in this order:

1. The `power_source` key on the bulb wins.
2. A power source block that names the group of the bulb claims the bulb.
3. The bulb is not power-aware. The bulb behaves as it does today.

A block accepts `group` or `members`. Exactly one of the two is permitted. A bulb belongs to a maximum of one power source. The validator follows the pattern of `_groups_valid` (`settings.py:107-122`).

**Availability.** `availability = offline` now has one meaning only: the bulb must answer, and the bulb does not answer. That is a real fault. An unpowered bulb is not offline; it is `powered = false`.

**Traffic.** While a power source is known to be off, wiz2mqtt skips the network read for its member bulbs and does not advance the failure counter (`_FAILURE_THRESHOLD`, `entity.py:20`).

**Legacy mapping.** `when_unreachable` moves from the bulb to the power source. On the power source it tells wiz2mqtt what an unreachable bulb means when there is no better evidence: `"fault"` (default) or `"no_power"`. `extra="forbid"` makes a stale bulb-level key a hard `ValidationError`. The migration maps a legacy bulb-level `when_unreachable = "off"` to an implicit single-bulb power source with `when_unreachable = "no_power"` and emits a warning that names the replacement. The repository has no deprecation precedent and no aliases.

**Field conventions.** A duration is a bare `float` in seconds, and the unit is stated in `description=`. A boolean uses the `enable_<noun>` form. Every new field carries `Field(description=...)`. `signal_topic` gets a validator that follows the cosalette `topic_prefix` check: reject `+` and `#`, restrict the character set, reject an empty value. `docs/configuration.md` is hand-maintained and must be edited by hand.

```toml
queued_command_ttl = 86400.0          # seconds

[[bulbs]]
name = "living-room"
ip = "192.168.1.102"
power_source = "downstairs-circuit"   # optional; beats any group reference
restore_previous_state = true         # default false

[[power_sources]]
name = "downstairs-circuit"
group = "downstairs"                  # or members = [...], exactly one
signal_topic = "openhab/relay/downstairs/state"   # optional
when_unreachable = "fault"            # "fault" (default) or "no_power"
enable_power_on_request = true        # default false
enable_power_off_request = false      # default false
power_off_idle_delay = 600.0          # seconds
wiz_bulbs_only = false                # must be true before a power-off request
```

## Decision Drivers

- A consumer must tell "unpowered" from "faulty". Today both states look the same on the wire
- The business logic in openHAB must stay simple: `state AND powered` from one message, with no join across topics
- The signal is optional. The feature must work on a circuit that has no relay at all
- A lighting group matches a circuit most of the time, but not always. The exceptions need an escape hatch, not a second inventory
- An absent bulb costs 13 s of a held pywizlight lock per cycle. A known-dark circuit must not be read at all
- Intent is more valuable than reality. A payload that carries the desired state lets a consumer recover reality; the reverse is not true

## Considered Options

### Option 1: Raw signal, OFF while unpowered, per-bulb key only

Republish the raw relay signal as the `powered` value (source option a). Publish `state = OFF` for a bulb while its circuit is unpowered (state option a). Address the circuit with a `power_source` key on every bulb, with no block of its own (addressing option a).

- *Advantages:* The smallest code change: no belief, no block, no resolution order; The `powered` value is a pure passthrough, so it is easy to explain; `OFF` is a value that every consumer already understands
- *Disadvantages:* A circuit with no relay signal has no `powered` value at all, so the feature does not work there; `OFF` erases the intent. When the circuit returns, nothing on the wire says what the bulb should show; A raw signal that is stale or wrong contradicts a bulb that answers, and the consumer has no rule to break the tie; The `power_source` key must be repeated on every bulb of a circuit, and the circuit-level settings (signal topic, requests) have no home

### Option 2: Derived belief, desired state plus powered, power_sources block with override (chosen)

Publish a derived belief where an answering bulb outranks the signal (source option b). Publish the desired state plus a `powered` key while the bulb is unpowered (state option b). Declare a `[[power_sources]]` block with `group` or `members`, and let a per-bulb `power_source` key override the group reference (addressing option b).

- *Advantages:* Works with no relay signal: one answering bulb sets the belief to `on`; `state AND powered` gives the lit state from one message, and the desired state is still on the wire for the restore; `availability = offline` regains one meaning: a real fault; The block gives the circuit-level settings a home, and the per-bulb key handles the exception where a group and a circuit differ; A known-dark circuit skips the network read, which saves 13 s of a held lock per absent bulb per cycle
- *Disadvantages:* `powered` is a new key outside the Home Assistant JSON light schema, so ADR-001 must adopt it; A belief is derived, so a consumer must trust the rules of wiz2mqtt instead of a raw sensor; The bulb-level `when_unreachable` moves to the power source, which is a configuration change

### Option 3: Per-bulb flag, unknown while unpowered, groups reuse

Publish no source-level entity; only a per-bulb `powered` flag exists (source option c). Publish `state = unknown` while the bulb is unpowered (state option c). Reuse `[[groups]]` with extra keys such as `signal_topic` instead of a new block (addressing option c).

- *Advantages:* No new inventory block; the operator edits a block that already exists; `unknown` is honest about what wiz2mqtt can observe; No source-level entity to announce, so the discovery surface stays as it is
- *Disadvantages:* `unknown` erases the intent in the same way `OFF` does; A group is a consumer-side fan-out construct (ADR-003). Power keys on a group change its meaning, and a bulb whose circuit differs from its group has no override; No source-level entity means no place to publish the belief or the desired power (ADR-009); The rule `state AND powered` still needs a `powered` value, and a per-bulb flag cannot express evidence from a peer bulb on the same circuit

## Decision Matrix

| Criterion | Raw signal, OFF while unpowered, per-bulb key only | Derived belief, desired state plus powered, power_sources block with override | Per-bulb flag, unknown while unpowered, groups reuse |
| --- | --- | --- | --- |
| A consumer can tell unpowered from faulty | 3 | 5 | 3 |
| openHAB rule stays one expression on one message | 4 | 5 | 3 |
| Works with no relay signal | 1 | 5 | 2 |
| Intent survives an outage (reality recoverable from the payload) | 1 | 5 | 1 |
| Handles a circuit that differs from a lighting group | 4 | 5 | 1 |
| Traffic saving on a dark circuit | 4 | 5 | 3 |
| Size of the configuration change | 4 | 3 | 4 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- A consumer tells "unpowered" from "faulty" from one retained message: `powered = false` versus `availability = offline`
- The openHAB rule for "the lamp is lit" is `state AND powered`, with no join across topics
- The `powered` flag works on a circuit with no relay, because an answering bulb sets the belief to `on`
- `availability = offline` means a real fault only
- A known-dark circuit costs no network reads and no failure counts; the 13 s lock hold per absent bulb per cycle disappears
- The per-bulb `power_source` key handles the exception where a lighting group and a circuit differ
- A legacy `when_unreachable = "off"` on a bulb still starts, with a warning that names the replacement

### Negative

- `powered` is a new key that ADR-001 must adopt. It sits outside the Home Assistant JSON light schema, like the existing `hsb` key
- The bulb-level `when_unreachable` moves to the power source, which is a configuration change for every operator who set it
- A bulb on a source with no signal and no answering peer stays `unknown`; wiz2mqtt cannot say more than it can observe
- The belief is derived, so a wrong rule in wiz2mqtt shows as a wrong `powered` value on every member bulb at once

_2026-09-13_

## Amendment (2026-09-14) — Additive

**Membership.** Resolve each bulb once: explicit `power_source`; then a source whose `members` contains it; then a source whose `group` contains it; otherwise none. Reject ambiguous implicit claims, including `members`/`group` overlap. Explicit references must name a source and override implicit claims.

**Signal contract.** `signal_topic` is a retained status input, never a command surface. Accept only UTF-8 `on` or `off` (lowercase, whitespace trimmed once); ignore and warn on every other payload without echoing it, leaving belief unchanged. A topic is unique per source. Broker ACLs permit only the configured controller to publish it; wiz2mqtt subscribes and never publishes there.

**Source contract.** Each source is one retained `wiz2mqtt/{source}/state` device payload: `{\"powered\": \"on\" | \"off\" | \"unknown\", \"power_request\": \"on\" | \"off\" | null, \"members\": [...]}`. It exposes the first field as the power binary sensor and the second as the diagnostic desired-power binary sensor. Source names must not collide with bulb or group names.
