# Mains Power Awareness

Some WiZ bulbs sit behind a smart relay or a classic wall switch. When the circuit has
no mains power, every bulb on it goes dark and stops answering at the same time. When
the power comes back, each bulb boots into its factory default.

wiz2mqtt can model such a circuit as a **power source**. Then it can:

- tell an unpowered bulb from a faulty bulb,
- keep what the bulb should show while it is dark,
- give the bulb its state back when it returns,
- ask the relay for power (optional).

The decisions behind this page are
[ADR-007](adr/ADR-007-mains-power-awareness-through-power-sources.md) (power sources and
the belief), [ADR-008](adr/ADR-008-desired-state-with-restore-on-return-to-reachability.md)
(the desired state and the restore) and
[ADR-009](adr/ADR-009-power-requests-as-a-retained-desired-power-state.md) (power
requests). The key reference is in [Configuration](configuration.md#power-sources).

## Concepts

### Powered is not on

Two values describe a bulb in a power source. They answer different questions.

| Key in `wiz2mqtt/{bulb}/state` | Question                                     | Values                  |
| ------------------------------ | -------------------------------------------- | ----------------------- |
| `state`                        | What does the bulb show, or what should it show? | `"ON"`, `"OFF"`         |
| `powered`                      | Does the circuit of the bulb have mains power?   | `true`, `false`, `null` |

A bulb is **lit** when `state == "ON"` and `powered == true`. Both keys are in one
retained message, so a consumer needs no join across topics.

While wiz2mqtt cannot see the bulb, `state` is the **desired** state, not `"OFF"`. An
unpowered bulb that should be on publishes `{"state": "ON", "powered": false}`. The
reason: you can calculate reality from intent (`state` and `powered`), but you cannot
calculate intent from reality.

`powered` is `null` for a bulb outside every power source, and for a bulb whose source
belief is `unknown`.

### The belief

A power source publishes what wiz2mqtt **believes** about the circuit, not the raw relay
signal. The belief has three values: `on`, `off` and `unknown`. wiz2mqtt applies three
rules, in this order:

1. If one or more member bulbs answered after the last change of the signal, the
   belief is `on`. New evidence from a bulb outranks the signal.
2. If no member answered after the last change of the signal and the source has a
   signal, the belief is the signal.
3. If no member answers and there is no signal, `when_unreachable` decides: `unknown`
   for `fault` (the default), `off` for `no_power`.

Rule 1 makes the feature work on a circuit without a relay signal. A member counts as
"not answering" only after three failed reads in a row. One lost read does not change
the belief.

A change of the signal makes each earlier answer old. Thus a signal `off` sets the
belief `off` at once. If a member answers after the signal, the belief is `on` again. A
repeat of the same signal is not a change.

The signal also starts one read of each member. That read polls the bulb and does not
use a push that arrived before the signal. On a live circuit, a wrong signal `off` thus
shows `powered: false` normally for less than 1 s.

### Availability means a fault

`wiz2mqtt/{bulb}/availability` is `offline` only when the bulb must answer and does
not answer. That is a real fault.

- If the belief is `off`, the bulb stays `online` with `powered: false`. wiz2mqtt also
  stops reading the bulb after the third failed read, until the belief changes or the
  bulb boots. While a signal `off` decides the belief, one failed read is sufficient.
- If the belief is `on` or `unknown`, three failed reads in a row set the bulb
  `offline`.

### The desired state

Each bulb has one desired state. wiz2mqtt keeps it in its store file, so it survives a
restart. Two writers change it, and the newer write wins:

- A command on `wiz2mqtt/{bulb}/set`, at all times.
- An observation of the bulb, but only in the steady phase (see below). Thus a change
  that you make in the WiZ app becomes the new desired state.

The desired state never expires.

### Phases and the return path

A reachable bulb is in one of two phases:

- **Steady.** The bulb confirmed the last state that wiz2mqtt wrote. An observation
  counts as intent.
- **Reconnect.** The bulb came back, and wiz2mqtt did not yet confirm the intent. No
  observation counts as intent. This stops the factory default of a booted bulb from
  erasing the intent.

```mermaid
stateDiagram-v2
    Steady --> Unreachable: third failed read in a row
    Unreachable --> Reconnect: firstBeat, or a read succeeds and a desired state exists
    Steady --> Reconnect: firstBeat, then a read differs from the desired state
    Unreachable --> Steady: a read succeeds and no desired state exists
    Reconnect --> Steady: the return path writes, and a read-back confirms it
    Reconnect --> Reconnect: three write attempts fail (error, the intent is kept)
```

`firstBeat` is a broadcast that a WiZ bulb sends when it boots. It only wakes the
bulb's next read. It does not write to the bulb. WiZ repeats the broadcast during
startup, so for a bulb that still answers, `firstBeat` starts the reconnect phase only
until a return-path write is confirmed, or while a command waits in the queue.

After that, a `firstBeat` from a bulb that still answers can be a repeated broadcast or
a quick power cycle that missed no read, for example a wall switch flicked off and on
with no power source configured. wiz2mqtt reads the bulb at once, bypassing the cache,
and compares the answer with the desired state, with the same tolerances as a read-back.
If they differ, the bulb lost its state and the reconnect phase starts. If they match,
nothing is written. If the read fails, for example while the bulb still boots, the
check waits for the next successful read and the failed read counts as usual.

Each time a bulb enters the reconnect phase, wiz2mqtt logs one `INFO` line with the
reason, for example `Bulb desk: entering reconnect phase (first_beat)`:

| Reason            | Trigger                                                                     |
| ----------------- | --------------------------------------------------------------------------- |
| `first_tick`      | The bulb's first tick after a start found a stored desired state.           |
| `slow_recovery`   | A read succeeded after the bulb had failed three reads, without `firstBeat`. |
| `settle_conflict` | A read inside the `restore_settle` window differed from the restored state. |
| `first_beat`      | The bulb sent `firstBeat`.                                                  |
| `boot_grace`      | A `/set` arrived inside the power source's `boot_grace` window.             |
| `write_timeout`   | A direct `/set` write timed out or could not connect.                       |

After the first successful read in the reconnect phase, exactly one of these actions
occurs:

1. If a command waits in the queue and it is not older than `queued_command_ttl`,
   wiz2mqtt applies the command. The queue is always on.
2. Else, if `restore_previous_state = true` and a stored desired state exists,
   wiz2mqtt applies the stored desired state.
3. Else, wiz2mqtt accepts the state that the bulb reports as the new desired state.

A write to restore `OFF` sends only `OFF`. A write to restore `ON` sends `ON` and the
appearance (brightness, colour or scene) in one command. The command carries one colour
mode: a bulb that runs a scene can also report a colour temperature, and the scene wins.
wiz2mqtt reads the state back after each write. The comparison allows for the bulb's own rounding: brightness in whole
percent, the 10 % minimum that WiZ firmware applies to a dimmer write, and the hue of a
very pale colour. Any hue confirms for white (saturation
`0`). It tries a maximum of three times in total. If all three attempts
fail, it publishes an error on `wiz2mqtt/{bulb}/error`, keeps the desired state and
stays in the reconnect phase, so the next tick or `firstBeat` runs the return path
again.

A write that the bulb cannot express (`WizUnsupportedCommandError`, for example a
scene the bulb does not have) is not retried. wiz2mqtt publishes a terminal
`restore_unconfirmed` error after one attempt, accepts the state that the bulb reports
as the new desired state and leaves the reconnect phase. A command that waits in the
queue keeps the phase, so the next tick writes it.

A `/set` in the reconnect phase goes to the bulb at once when the bulb has answered
its last read. The next tick then runs the return path, which writes the desired state
that the command has updated and reads it back, so the command counts as the restore.
The command waits in the queue instead while the bulb has not answered yet, while its
last answer predates the power source's last signal change, or while the return path
is writing to the bulb, so that a write retry cannot overwrite the command.

## Operator guide

### Declare a power source

Declare the circuit and its members with `group` or with `members`, not both:

```toml
[[groups]]
name = "downstairs"
members = ["living-room", "kitchen", "hall"]

[[power_sources]]
name = "downstairs-circuit"
group = "downstairs"            # every bulb of the group

[[power_sources]]
name = "porch-circuit"
members = ["porch"]             # or name the bulbs directly
```

If one bulb of a group sits on a different circuit, set `power_source` on that bulb:

```toml
[[bulbs]]
name = "hall"
ip = "192.168.1.104"
power_source = "porch-circuit"  # wins over the group claim above
```

wiz2mqtt resolves the source of each bulb in this order:

1. The `power_source` key on the bulb.
2. A source whose `members` names the bulb.
3. A source whose `group` contains the bulb.
4. No source: the bulb has no power awareness and `powered` is always `null`.

A bulb belongs to a maximum of one source. If two sources claim the same bulb through
`members` or `group`, wiz2mqtt does not start.

### Connect a relay signal

`signal_topic` is optional. Without it, the belief comes from the bulbs alone. With it,
wiz2mqtt knows why a whole circuit is dark.

- wiz2mqtt accepts only the payloads `on` and `off`, in lowercase, after one trim of
  whitespace. It ignores any other payload and logs a warning.
- Publish the signal **retained**. After a restart, wiz2mqtt reads the last signal from
  the broker. A non-retained signal stays unknown until the relay changes again.
- The topic must not be below the topic prefix of wiz2mqtt, and each source needs its
  own topic.
- Give write access to the relay publisher only. wiz2mqtt needs read access only
  (`cosalette schema acl` generates this rule).

An openHAB rule that publishes a relay item as the signal:

```java
rule "Downstairs relay to wiz2mqtt signal"
when
    Item Downstairs_Relay changed
then
    val mqtt = getActions("mqtt", "mqtt:broker:broker")
    mqtt.publishMQTT("openhab/relay/downstairs/state",
        Downstairs_Relay.state.toString.toLowerCase, true)
end
```

### Choose `when_unreachable`

`when_unreachable` on a power source tells wiz2mqtt what an unreachable bulb means when
it has no better evidence (no answering member and no signal).

| Value             | Belief    | Availability of the unreachable bulb | Use it when                                                  |
| ----------------- | --------- | ------------------------------------ | ------------------------------------------------------------ |
| `fault` (default) | `unknown` | `offline` after three failed reads   | The circuit is normally on, and a dark bulb means a problem. |
| `no_power`        | `off`     | stays `online`                       | A wall switch cuts the circuit often, and that is normal.    |

### Restore and queue

- `restore_previous_state = true` on a bulb makes wiz2mqtt write the stored desired
  state back after the bulb boots. The default is `false`: the bulb keeps its factory
  default, and that becomes the new desired state.
- The queue is always on. A command that arrives while the bulb is unreachable is
  applied when the bulb returns, also with `restore_previous_state = false`.
- `queued_command_ttl` (top level, in seconds, default `86400`) is the maximum age of
  a queued command. wiz2mqtt drops an older command and writes a log line. A bulb or
  a power source can override it with its own `queued_command_ttl`; the bulb's value
  wins, then the power source's, then the top-level value.
- A `/set` that times out publishes `error_type: "timeout_queued"`. The command is
  still in the queue. If the return path cannot confirm the write after three
  attempts, the error carries `error_type: "restore_unconfirmed"`.
- `restore_retry_delays` (top level or per power source, default `[2.0, 5.0]`) spaces
  the three attempts, so a bulb that answers before its firmware applies writes still
  confirms on the second or third attempt.

### Switched relays

A bulb behind a relay needs a few seconds to boot after the relay turns on. Without
more configuration, a command in that window times out, and failed reads count
towards `offline`. Three power-source keys make a switched circuit behave:

- `boot_grace` (seconds, default `0` = off) opens a window when the signal changes to
  `on`. Until a member bulb answers, wiz2mqtt queues a command for it without a wire
  attempt, and a failed read does not count towards `offline`. The queued command is
  applied as soon as the bulb answers. The window needs a `signal_topic`; set it a
  little above the boot time of your bulbs, for example `20`.
- `restore_settle` (seconds, default `15`) writes the restored state again when the
  bulb reports something else shortly after a confirmed restore. A change in the WiZ
  app, with a WiZ remote or by a WiZ room sync in that window is therefore reverted;
  after it, the change becomes the new desired state. A wiz2mqtt command ends the
  window: it is new intent and is never reverted. `0` switches the window off.
- `clear_queue_on_power_off = true` (default `false`) drops the members' queued
  commands when the signal changes from `on` to `off`. Use it when switching the relay
  off means "forget what was asked". A command queued while the signal is already
  `off` survives, so a command followed by a power-on request still works.

The defaults keep the earlier behaviour: no grace window and no clearing.

### Power requests

A power source can ask for a change of its circuit. wiz2mqtt publishes the request
retained in `wiz2mqtt/{source}/state` as `power_request`. It never operates the relay
itself. Your consumer maps the request to the relay.

- `enable_power_on_request = true`: an accepted command that makes a member bulb
  desired `ON` while the belief is `off` gives `power_request: "on"`.
- `enable_power_off_request = true`: when every member has been desired `OFF` for
  `power_off_idle_delay` seconds (default `600`), wiz2mqtt publishes
  `power_request: "off"`. This direction needs `wiz_bulbs_only = true`.
- `power_request: null` means "no request". wiz2mqtt clears a request when the belief
  agrees with it, or when the request does not apply any more.

!!! warning "Do not set `enable_power_off_request` on a circuit with other loads"
    While the key is set, wiz2mqtt owns the relay. A user who switches the relay by
    hand fights the idle timer. `wiz_bulbs_only = true` is your statement that no fan,
    socket or other lamp is on the circuit.

The retained request stays on the broker when wiz2mqtt stops. That is intended: a
consumer that connects later still reads the current request. At startup, wiz2mqtt
publishes `null` first and then calculates the request again from the belief. Thus a
restart alone never cuts a circuit.

#### The consumer contract

A consumer that maps the power-on request to a relay can rely on these rules:

1. **Opt in per source.** Without `enable_power_on_request = true` the request is
   always `null`.
2. **Only a command raises it.** A read, a bulb boot or a relay signal never raises a
   request. The command is queued before the request is published, so the bulb applies
   it as soon as it boots.
3. **Only a dark circuit.** The belief must be `off`. A belief of `unknown` never
   raises a request. With `when_unreachable = "fault"` and no `signal_topic`, the
   belief is never `off`, so use `no_power` or connect a relay signal.
4. **The command must want light.** `state: "ON"` does, and so does any command
   without a `state` key that changes something (brightness, colour, colour
   temperature, effect or effect speed), because the bulb switches on to apply it.
   `state: "OFF"`, and brightness `0` (which means OFF), never do.
5. **Release on convergence, never on a timeout.** wiz2mqtt sets the request back to
   `null` when the belief becomes `on`, or when no member is desired `ON` any more. With
   a `signal_topic` the release follows the relay's `on` at once. Without one, it
   follows the first answer of a member bulb. A slow relay still sees the request, so
   the consumer needs no retry of its own.
6. **wiz2mqtt never actuates the relay.** It publishes nothing to the relay's topic or
   to the `signal_topic`. One rule on `changed` of the request is all the consumer
   needs: see the [openHAB recipe](#openhab) and the
   [Home Assistant recipe](#home-assistant).

### Migrate a bulb-level `when_unreachable`

Earlier releases had `when_unreachable` on the bulb. wiz2mqtt still starts with it,
and logs one warning per bulb. For a bulb `lamp` with `when_unreachable = "off"`, the
warning is:

```text
Bulb lamp: when_unreachable = 'off' is replaced by power_source = 'lamp-power' (see [[power_sources]] name = 'lamp-power', when_unreachable = 'no_power'); update wiz2mqtt.toml
```

Replace the bulb key with the block that the warning names:

```toml
[[bulbs]]
name = "lamp"
ip = "10.0.0.11"
power_source = "lamp-power"

[[power_sources]]
name = "lamp-power"
members = ["lamp"]
when_unreachable = "no_power"
```

For `when_unreachable = "unavailable"`, remove the key. That behaviour is now the
default for a bulb outside every power source. The next release removes this migration,
and a bulb-level `when_unreachable` then stops wiz2mqtt at startup.

### Keep the store on a volume

The desired state is in the store file; queued commands are in memory only and
are lost on restart. Set `WIZ2MQTT_STORE_PATH` to a path inside a mounted volume.
If the file is in the container layer, a container restart loses every desired
state, and `restore_previous_state` has nothing to restore. The shipped `compose.yml` sets
`WIZ2MQTT_STORE_PATH=/app/data/store.json` on the `wiz2mqtt-data` volume.

## Consumer recipes

### openHAB

Generate the Things and Items as described in
[openHAB generation](configuration.md#openhab-generation). For each power source you
get two read-only Items. For each bulb in a source, you get one more read-only Item:

| Item                               | Meaning                                         |
| ---------------------------------- | ----------------------------------------------- |
| `Wiz2Mqtt_<Source>_Powered`        | The belief: `ON`, `OFF`, or `NULL` for unknown  |
| `Wiz2Mqtt_<Source>_PowerRequest`   | The request: `ON`, `OFF`, or `NULL` for none    |
| `Wiz2Mqtt_<Bulb>_Powered`          | The belief of the bulb's source                 |

!!! note "`NULL` needs openHAB 5.1 or later"
    The generated channels use the `nullValue` parameter for `unknown` and JSON `null`.
    A switch channel supports it from openHAB 5.1. openHAB 5.0 logs a warning and keeps
    the last value. openHAB sets `NULL`, not `UNDEF`: the MQTT binding cannot set
    `UNDEF` from a message. To test for "no value", use `instanceof UnDefType`.

**Lit.** Calculate "lit" from the two Items of one bulb:

```java
rule "Living room lit"
when
    Item Wiz2Mqtt_LivingRoom_State changed or
    Item Wiz2Mqtt_LivingRoom_Powered changed
then
    LivingRoom_Lit.postUpdate(
        if (Wiz2Mqtt_LivingRoom_State.state == ON &&
            Wiz2Mqtt_LivingRoom_Powered.state == ON) ON else OFF)
end
```

**The relay.** Your relay Item stays the main light switch that users operate.
wiz2mqtt does not generate a relay Item or a rule. To let wiz2mqtt ask for power, map
the request to the relay:

```java
rule "Downstairs circuit follows the wiz2mqtt power request"
when
    Item Wiz2Mqtt_DownstairsCircuit_PowerRequest changed
then
    val request = Wiz2Mqtt_DownstairsCircuit_PowerRequest.state
    if (request == ON || request == OFF) {
        Downstairs_Relay.sendCommand(request as OnOffType)
    }
end
```

The rule triggers on `changed`, not on `received update`. Thus a repeat of the retained
message (MQTT 5 refresh) does not send the command again. `NULL` means "no request", so
the rule does nothing.

The request follows [the consumer contract](#the-consumer-contract). In openHAB terms:
`ON` on the `State` Item asks for power, and so does a `Brightness`, `Color`,
`ColorTemp`, `Effect` or `EffectSpeed` command, such as a move of the brightness
slider. `OFF` on the `State`, `Brightness` or `Color` Item never does, because openHAB
sends it as brightness `0`.

**Thing availability.** Each generated bulb Thing reads the availability topic of its
bulb. The Thing goes `OFFLINE` when the bulb publishes `offline`, and openHAB then does
not apply a command to the Item by autoupdate. Because an unpowered bulb stays
`online`, a command to it is still queued and applied when the power returns. Only a
real fault makes the Thing `OFFLINE`. This is a change for existing openHAB users: it
takes effect when you generate your Things again.

### Home Assistant

wiz2mqtt announces its entities through MQTT discovery. You configure nothing.

- **The light** is a JSON-schema light with a state topic. Home Assistant shows the
  state that wiz2mqtt publishes, which is the desired state while the bulb is dark. Do
  not set `optimistic: true` in an override. It makes the entity `assumed_state`, and
  Home Assistant then shows two buttons instead of a toggle.
- **Each power source** is one device with two binary sensors:

  | Entity          | Class                           | `on`                        | `off`                      | Unknown           |
  | --------------- | ------------------------------- | --------------------------- | -------------------------- | ----------------- |
  | `powered`       | `device_class: power`           | The belief is `on`          | The belief is `off`        | Belief `unknown`  |
  | `power_request` | `entity_category: diagnostic`   | wiz2mqtt asks for power     | Off request, or no request | never             |

  Both are read-only. wiz2mqtt never announces a switch for a circuit.

**Lit.** This MQTT binary sensor calculates "lit" from the one bulb message. Replace
`living-room` with the name of your bulb:

```yaml
mqtt:
  binary_sensor:
    - name: "Living room lit"
      unique_id: wiz2mqtt_living_room_lit
      device_class: light
      state_topic: "wiz2mqtt/living-room/state"
      availability_topic: "wiz2mqtt/living-room/availability"
      value_template: >-
        {% if value_json.state != 'ON' or value_json.powered == false %}OFF
        {%- elif value_json.powered %}ON
        {%- else %}None{% endif %}
```

The template gives `OFF` if the bulb should be off or has no power, `ON` if it should
be on and has power, and unknown if the belief is unknown.

## Timing

| Event                                                   | Expected time                                                                  |
| ------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Power returns, `firstBeat` reaches the host             | The restore starts less than 1 s after the bulb boots.                         |
| Power returns, no `firstBeat` (for example, no host networking) | The restore starts on the next heartbeat read, a maximum of 60 s later. |
| Circuit goes dark, no signal                            | 159 s to 219 s until the belief changes; 192 s to 252 s on a host that receives idle pushes from the bulbs. |
| Circuit goes dark, signal `off` arrives                 | At once: the belief becomes `off`. wiz2mqtt stops reading a member after its first failed read, about 13 s after the signal. |
| Signal `on` arrives while no member answers             | At once: the belief becomes `on`.                                              |
| Command inside `boot_grace` after signal `on`           | At once: queued, no wire attempt; applied when the bulb answers.              |

A failed read takes 13 s (the pywizlight timeout), and the heartbeat waits 60 s after
each read. Without a signal, three failed reads in a row are necessary before a bulb
counts as not answering.
