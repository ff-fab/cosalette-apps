---
status: Accepted
date: 2026-09-13
impact: moderate
tags: [mqtt, devices, configuration, architecture]
---

# ADR-009: Power Requests as a Retained Desired Power State

## Status

Accepted **Date:** 2026-09-13

## Context

ADR-007 gives wiz2mqtt a belief about the mains power of each power source. A belief alone cannot bring a dark circuit up. When a user sends a command for a bulb on a dark circuit, the command is queued (ADR-008) and waits until somebody flips the wall switch. The user asked for a fourth feature (C, the lowest priority): wiz2mqtt asks the relay for power.

The relay is owned by openHAB or Home Assistant. In openHAB the "main light switch" item controls the relay, and that item is what the user operates from the wall and from the app. wiz2mqtt has no direct access to the relay. It can only publish a request that the controller acts on.

Three risks shape the design. A missed message must not strand the relay: MQTT delivers a pulse once or not at all, and a pulse that is lost leaves no trace. A control that looks like a switch invites a user to operate it, and then two writers fight over the relay. A power-off must never cut a load that is not a WiZ bulb, because a circuit can carry a fan, a socket, or a non-WiZ lamp.

The Home Assistant `binary_sensor` platform has a `power` device class and a `diagnostic` entity category. Both are read-only.

The design was settled in the design interview (decisions Q12, Q13, Q19).

## Decision

Publish a power request as a **retained desired power state** per power source, opt-in per direction, and announce only read-only entities.

**Direction.** Three options were weighed: (a) no requests; (b) power-on only; (c) power-on and power-off, each opt-in. Option (c) is chosen. `enable_power_on_request` and `enable_power_off_request` are per-source booleans with a default of `false`.

- A command for a bulb on a dark circuit raises a power-on request.
- A power-off request fires after every bulb on the source is off for `power_off_idle_delay` (a bare float in seconds).
- A power-off request needs `wiz_bulbs_only = true`. That key is a declaration by the operator that no other load sits on the circuit. Without it, no power-off request fires.

**Request shape.** Two options were weighed: (a) a pulse or command message; (b) a retained desired power state. Option (b) is chosen. A retained state is idempotent and self-healing: a consumer that missed a message reads the current request on its next subscribe, and a repeated publish changes nothing. The stated and accepted consequence: while `enable_power_off_request` is set, wiz2mqtt owns the relay.

**Entities.** Two options were weighed: (a) a switch; (b) two read-only binary sensors. Option (b) is chosen. Each power source announces:

- The belief (ADR-007), as a `binary_sensor` with the device class `power`.
- The desired power, as a second `binary_sensor` in the diagnostic category.

Never announce a switch. A switch invites a user to fight the state machine.

**openHAB.** The "main light switch" that controls the relay stays the item that the user operates. wiz2mqtt reports the powered state, and wiz2mqtt requests a change. wiz2mqtt does not replace the item. The consumer turns the desired power into a relay command.

```toml
[[power_sources]]
name = "downstairs-circuit"
group = "downstairs"
signal_topic = "openhab/relay/downstairs/state"
enable_power_on_request = true        # default false
enable_power_off_request = true       # default false; needs wiz_bulbs_only
power_off_idle_delay = 600.0          # seconds
wiz_bulbs_only = true                 # operator declaration: no other load
```

## Decision Drivers

- A command for a dark circuit must be able to bring the circuit up, or the queued command of ADR-008 waits for a wall switch
- A request must be idempotent, so a missed message does not strand the relay in the wrong state
- wiz2mqtt must never invite a user to fight the state machine. A control that looks operable will be operated
- A power-off must never cut a load that is not a WiZ bulb
- Each direction carries a different risk, so each must be opt-in on its own

## Considered Options

### Option 1: No requests, belief sensor only

wiz2mqtt reports the belief (ADR-007) and never asks for power (direction option a). No request shape and no desired-power entity exist.

- *Advantages:* No relay ownership, so no operational risk; No new wire contract beyond the belief; Nothing for the operator to declare
- *Disadvantages:* A command for a dark circuit waits for a wall switch, so feature C is not delivered; The queued command of ADR-008 can expire before anybody flips the switch; A dark circuit stays dark even when the user clearly wants light

### Option 2: Power-on only as a pulse command, announced as a switch

Ask for power on only, never for power off (direction option b). Publish the request as a one-shot command message (shape option a). Announce the request as a `switch` entity so a user can also trigger it (entities option a).

- *Advantages:* No power-off, so no risk of cutting a foreign load; A pulse maps one-to-one onto an openHAB command item; A switch is a familiar control in both consumers
- *Disadvantages:* A pulse that is lost leaves no trace; a consumer that reconnects later never learns about it; A switch invites a user to operate it, and then the user and the state machine fight over the relay; A circuit that wiz2mqtt turned on is never turned off, so a `wiz_bulbs_only` circuit idles powered; A switch entity implies a state that wiz2mqtt does not own

### Option 3: Power-on and power-off opt-in as a retained desired power state, two read-only binary sensors (chosen)

Ask for power on and for power off, each opt-in per power source (direction option c). Publish the request as a retained desired power state (shape option b). Announce the belief as a `binary_sensor` with device class `power` and the desired power as a diagnostic `binary_sensor`; never a switch (entities option b).

- *Advantages:* A retained state is idempotent and self-healing; a missed message is recovered on the next subscribe; Read-only entities give the user nothing to fight with; The `wiz_bulbs_only` guard makes a power-off an explicit operator declaration; The openHAB main light switch stays the item the user operates; wiz2mqtt adds a request, not a replacement
- *Disadvantages:* While `enable_power_off_request` is set, wiz2mqtt owns the relay; A retained request outlives a wiz2mqtt restart and must be documented as intended; A consumer needs a rule to turn the desired power into a relay command

## Decision Matrix

| Criterion | No requests, belief sensor only | Power-on only as a pulse command, announced as a switch | Power-on and power-off opt-in as a retained desired power state, two read-only binary sensors |
| --- | --- | --- | --- |
| A command can bring a dark circuit up | 1 | 4 | 5 |
| Robust against a missed message | 5 | 1 | 5 |
| No invitation to fight the state machine | 5 | 1 | 5 |
| Cannot cut a foreign load | 5 | 5 | 4 |
| Operational risk of relay ownership | 5 | 3 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- A command for a bulb on a dark circuit brings the circuit up, when the operator opts in
- A retained request is idempotent, so a lost message does not strand the relay
- The user has no switch to fight; the belief and the desired power are read-only
- A power-off cannot fire on a circuit that the operator did not declare as `wiz_bulbs_only`
- The openHAB main light switch stays the item the user operates

### Negative

- Relay ownership is a real operational risk: if the operator misdeclares `wiz_bulbs_only`, a power-off request cuts a foreign load
- A retained request outlives a wiz2mqtt restart. This is intended, but it must be documented so an operator does not read it as a stale value
- The consumer needs a rule that maps the desired power to the relay; wiz2mqtt cannot ship that rule

_2026-09-13_
