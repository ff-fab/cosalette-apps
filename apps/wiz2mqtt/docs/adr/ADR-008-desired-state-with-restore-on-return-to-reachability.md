---
status: Accepted
date: 2026-09-13
impact: moderate
tags: [persistence, lifecycle, devices, architecture, error-handling]
---

# ADR-008: Desired State With Restore on Return to Reachability

## Status

Accepted **Date:** 2026-09-13

## Context

A WiZ bulb that loses mains power boots into its factory default when the power returns. In a mixed environment a wall switch cuts and restores the circuit many times a day, and each time the bulb forgets its colour and its scene. The user wants the delay between "the bulb is online" and "the bulb shows its colour" to be as short as possible.

A bulb needs time to boot and to join the Wi-Fi network after it gets mains power. Measured on real hardware: a bulb returns in 0.5 s to 21 s when push works, and in 0 s to 62 s when push does not work. The power-on edge of a relay is therefore an early warning. It is never a green light. A restore that fires on the power edge either fails or waits on a guessed delay.

A WiZ bulb sends a `firstBeat` broadcast when it boots. `pywizlight/push_manager.py:131-132` routes the broadcast to the callback that `wizlight.set_discovery_callback(cb)` installs. wiz2mqtt installs no callback today, so the event is discarded. This is a sub-second signal that the bulb is available.

Two more facts shape the design. First, the user changes bulbs from the WiZ iOS app and from wall switches, so wiz2mqtt is not the only writer of intent. Second, a command that arrives while a bulb is unreachable is lost today. The user stated the caveat in the design interview (Q18):

> A state that is set while the bulb is offline must still be applied when the bulb goes online. The first report after the boot must not be read as a new intent.

pywizlight has no setter for the power-on behaviour of a WiZ bulb; `getUserConfig` and `getModelConfig` are read-only. So the restore must come from wiz2mqtt.

The design was settled in the design interview (decisions Q6 to Q10, Q18, Q24, Q25). ADR-007 records the power model that this ADR builds on.

## Decision

Keep one **desired state** per bulb, persist it in the cosalette device store, and restore it when the bulb returns to reachability. There is one state machine. The power signal of ADR-007 is an accelerator and an explanation. It is not a second mechanism.

**Restore trigger.** Three options were weighed: (a) the power-on edge of the signal; (b) the return to reachability, with `firstBeat` as the fast path; (c) a fixed delay after the power edge. Option (b) is chosen. The restore fires when the bulb answers again. `firstBeat` is the fast path that detects the return; wiz2mqtt installs a discovery callback with `set_discovery_callback` (ADR-006 amendment). The poll fallback of ADR-006 is the slow path.

**Intent capture.** Three options were weighed: (a) every observation is intent; (b) observations are intent in the steady phase only, never in the reconnect phase; (c) only commands are intent. Option (b) is chosen. Two writers write the desired state, and the newest write wins:

- An observation of the bulb, but only in the steady phase.
- A command, in any phase.

There are two phases:

- **Steady phase.** The bulb is reachable, and the bulb confirmed the last state that wiz2mqtt wrote. An observation counts as intent. This keeps a state that a user sets from the WiZ app or from another external source.
- **Reconnect phase.** The bulb returned, and wiz2mqtt did not yet confirm the intent. No observation counts as intent. This stops the boot default of the bulb from erasing the intent.

**Persistence.** Three options were weighed: (a) in memory only; (b) the cosalette device store; (c) a retained MQTT topic. Option (b) is chosen. The desired state survives a restart of wiz2mqtt. The desired state never expires (Q24).

**At a return, exactly one of three actions happens:**

1. A queued command waits: apply the queued command. This is always active.
2. There is no queued command, and `restore_previous_state` is set for the bulb: apply the stored desired state.
3. In all other conditions: accept the report of the bulb as the new desired state.

**The restore writes the on/off state, not only the appearance:**

- For `OFF`: send OFF first, and skip the appearance.
- For `ON`: send ON and the appearance in one command.

**Read-back.** After the write, read the state back. Retry a maximum of three times. If the retries are not sufficient, publish an error, leave the reconnect phase, and give the authority back to the lamp.

**Queue.** A command that arrives while the bulb is unreachable is queued. A queued command expires after `queued_command_ttl`, a top-level setting with a default of 86400 s. `restore_previous_state = false` does not disable the queue (Q25). A command that arrives while the bulb is offline is still applied at the return.

```python
# at a return to reachability (firstBeat or poll):
if queued is not None and not queued.expired(queued_command_ttl):
    await apply(queued)                       # feature D, always active
elif config.restore_previous_state:
    await apply(store.desired)                # feature B, opt-in per bulb
else:
    store.desired = observed                  # accept the report

# apply(): OFF first and no appearance; ON with appearance in one command;
# then read back, retry a maximum of three times, else publish an error
# and hand the authority back to the lamp.
```

## Decision Drivers

- The delay between "online" and "has its colour" must be as short as possible. `firstBeat` is sub-second; a poll is up to 60 s
- The newest intent wins, whether it comes from wiz2mqtt or from the WiZ app. wiz2mqtt is not the only writer
- A boot default must not erase the intent. The first report after a boot is the factory default, not a user choice
- A command set while the bulb is offline must apply at the return. Today it is lost
- A restore must not loop forever against a bulb that refuses. Three retries, then an error and a hand-back
- The intent must survive a restart of wiz2mqtt, or a restart during an outage loses every colour at once

## Considered Options

### Option 1: Power-edge trigger, every observation is intent, memory only

Fire the restore on the power-on edge of the relay signal (trigger option a). Treat every observation of the bulb as intent (capture option a). Keep the desired state in process memory only (persistence option a).

- *Advantages:* The simplest code: no phases, no store, no callback; The relay signal arrives before the bulb boots, so the intent is ready early; A user change from the WiZ app is captured at once
- *Disadvantages:* The power edge is an early warning, not a green light. The bulb is not reachable yet, so the restore fails or must guess a delay; The boot default of the bulb is an observation, so it overwrites the intent before the restore runs. This breaks the user caveat; A restart of wiz2mqtt during an outage loses every desired state; A circuit with no relay signal has no trigger at all

### Option 2: Reachability trigger with firstBeat, steady-phase observations only, device store (chosen)

Fire the restore on the return to reachability, with `firstBeat` as the fast path and the poll as the slow path (trigger option b). Treat an observation as intent in the steady phase only, never in the reconnect phase (capture option b). Persist the desired state in the cosalette device store (persistence option b).

- *Advantages:* The restore fires when the bulb can answer, and `firstBeat` makes that sub-second; The reconnect phase shields the intent from the boot default; the steady phase still accepts a change from the WiZ app; The desired state survives a restart of wiz2mqtt; One state machine for every bulb, with or without a relay signal; The same return path applies a queued command, so feature D needs no second mechanism
- *Disadvantages:* The device store becomes a hard dependency, which makes `cap-0d8y` a prerequisite; Two phases add a second mode to reason about and to test; wiz2mqtt must install a `set_discovery_callback`, a pywizlight surface it does not use today

### Option 3: Fixed delay after power edge, commands only as intent, retained MQTT topic

Fire the restore a fixed number of seconds after the power-on edge (trigger option c). Treat only commands as intent, never an observation (capture option c). Persist the desired state on a retained MQTT topic (persistence option c).

- *Advantages:* No reconnect phase is needed, because an observation never writes the intent; A retained topic survives a restart of wiz2mqtt and is visible on the broker; No pywizlight callback is needed
- *Disadvantages:* A fixed delay is either too short (the bulb is not up, measured up to 62 s) or too long (the user waits in the dark); A change from the WiZ app or a wall switch is never captured, so the next restore undoes the user; A retained topic is a second wire contract to document, and a consumer can write to it by mistake; A circuit with no relay signal has no trigger at all

## Decision Matrix

| Criterion | Power-edge trigger, every observation is intent, memory only | Reachability trigger with firstBeat, steady-phase observations only, device store | Fixed delay after power edge, commands only as intent, retained MQTT topic |
| --- | --- | --- | --- |
| Delay from reachable to restored | 2 | 5 | 2 |
| Newest intent wins, including a change from the WiZ app | 4 | 5 | 1 |
| Boot default cannot erase the intent | 1 | 5 | 5 |
| Intent survives a restart of wiz2mqtt | 1 | 5 | 4 |
| Works on a circuit with no relay signal | 1 | 5 | 1 |
| Simplicity of the state machine | 5 | 3 | 4 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- A bulb that returns shows its colour within a `firstBeat` round-trip when push works, instead of never
- A command sent while a bulb is dark applies at the return; the user does not have to send it again
- A change from the WiZ app or a wall switch is kept, because the steady phase accepts observations as intent
- The desired state survives a restart of wiz2mqtt
- One return path serves the queue, the restore and the accept rule, so there is one place to test
- A bulb that refuses three times gets an error and its authority back; wiz2mqtt does not loop

### Negative

- The device store becomes a hard dependency, which makes `cap-0d8y` (the store path outside the mounted volume) a prerequisite
- The reconnect phase adds a second phase to reason about, and every observation handler must know the phase
- A restore that fails three times leaves the lamp in its boot state until the next command
- `firstBeat` requires a `set_discovery_callback` in the adapter, so the restore fast path depends on the push return path of ADR-004
- A queued command that expires after `queued_command_ttl` is dropped without a wire-visible trace beyond the log

_2026-09-13_
