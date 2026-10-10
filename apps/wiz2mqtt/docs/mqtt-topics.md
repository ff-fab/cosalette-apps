# MQTT Topics

Unless you override `WIZ2MQTT_MQTT__TOPIC_PREFIX`, wiz2mqtt publishes under the
`wiz2mqtt/` root.

Each configured bulb gets three primary topics:

## Command Topic

**Topic:** `wiz2mqtt/<bulb>/set`

Send a partial JSON payload to change one or more fields. All fields are
optional, so both of these are valid:

```json
{"state": "ON", "brightness": 128}
```

```json
{"color_temp": 2700}
```

Supported keys:

| Key | Type | Notes |
| --- | ---- | ----- |
| `state` | `"ON"` or `"OFF"` | Power command |
| `brightness` | number `0..255` | Home Assistant brightness scale; a fractional value is rounded to the nearest integer. `0` means OFF (see below) |
| `color` | object `{r,g,b}` | RGB values `0..255` |
| `color_temp` | number `1..10000` | Kelvin; a fractional value is rounded to the nearest integer |
| `effect` | string | WiZ scene name (one of the advertised `effect_list`, e.g. `"Ocean"`) |
| `effect_speed` | number `10..200` | Scene animation speed; a fractional value is rounded to the nearest integer |
| `hsb` | string `"h,s,b"` | openHAB Color channel wire form |

`color`, `color_temp`, `effect`, and `hsb` are mutually exclusive. Invalid combinations
are rejected before the adapter is called.

A command without `state` that changes anything else also switches the bulb on,
because the bulb lights to apply it. wiz2mqtt records it as `state: "ON"`, so the
state topic, the desired state and a [power request](power-awareness.md#power-requests)
follow what the bulb does. An empty command `{}` changes nothing.

### Fractional numbers

`brightness`, `color_temp` and `effect_speed` accept a JSON number with a
fractional part and round it to the nearest integer. This exists for
percentage-scaling publishers: openHAB's Dimmer channel converts a percent
command onto the advertised `min`/`max` as `pct / 100 * 255`, which only
lands on a whole number at multiples of 20 % — a 30 % command arrives as
`76.5` and applies as `76`.

Rounding happens before the range check, so it does not widen the accepted
range: `-0.6` rounds to `-1` and is still rejected, as is `256.4`. Ties round to
the nearest even integer (Python's `round`), so `254.5` becomes `254`.

These fields take a JSON number only. `true`/`false`, a numeric string such
as `"128"`, and a non-finite number are rejected to the error topic. Otherwise
`false` or `"0"` would read as brightness `0` and switch the bulb off.

### Brightness 0 means OFF

A command whose brightness is `0` switches the bulb off and changes nothing
else, whatever other keys it carries. The brightness can come from the
`brightness` key (a fractional value below `0.5` included) or from the `b` of
an `hsb` triple. This is how openHAB sends OFF to a Dimmer
(`{"brightness":0}`) and to a Color channel (`{"hsb":"h,s,0"}`), so a group
OFF switches every bulb off instead of dimming it to the WiZ minimum. The
dimmest on level is `1`.

## State Topic

**Topic:** `wiz2mqtt/<bulb>/state`

The app publishes a retained JSON payload. `state`, `powered` and the
[command readiness](#command-readiness) keys are always present; the other
keys appear only when known for that bulb and mode.

Example RGB payload:

```json
{
  "state": "ON",
  "brightness": 128,
  "color_mode": "rgb",
  "color": {"r": 255, "g": 170, "b": 80},
  "hsb": "32,69,50"
}
```

Example color-temperature payload:

```json
{
  "state": "ON",
  "color_mode": "color_temp",
  "color_temp": 2700,
  "color_temp_kelvin": true
}
```

Optional state keys include `brightness`, `effect`, `effect_speed`, and
`power_draw_w`.

`powered` is always present. It is the belief of the bulb's power source:
`true`, `false`, or `null` when the belief is `unknown` or the bulb has no power
source. While wiz2mqtt cannot see the bulb, the payload carries the desired
state, not `"OFF"`. A bulb is lit when `state` is `"ON"` and `powered` is
`true`. See [Mains Power Awareness](power-awareness.md).

### Command readiness

Three more keys are always present. Together with `powered` they tell a
consumer whether the bulb has actually taken a command:

| Key | Value | Meaning |
| --- | ----- | ------- |
| `reachable` | `true` / `false` | The bulb itself answered, and not before its power source's last signal change. Like availability it is debounced: a live bulb stays `true` through isolated timeouts. |
| `pending` | object or `null` | The command queued while the bulb was out of reach (ADR-008). `null` when nothing is queued. |
| `last_applied` | object or `null` | The last queued or restored command wiz2mqtt wrote to the bulb on its return, and whether a read-back confirmed it. `null` until the first such write since wiz2mqtt started. |

`pending` carries `fields` (the `/set` field names the write will carry),
`queued_at` and `expires_at` (epoch seconds; the queue drops the command after
`queued_command_ttl`, so an `expires_at` in the past means the command will
not be sent). A queued OFF lists only `state`: the appearance queued
with it waits for a later ON. `last_applied` carries `at` (epoch seconds),
`fields`, `attempts` (1 to 3) and `confirmed`. When `confirmed` is `false`, no
read-back confirmed the write. wiz2mqtt keeps the desired state and retries on a
later tick or boot event.

A command to a dark bulb therefore shows up as, for example:

```json
{
  "state": "ON",
  "brightness": 200,
  "powered": false,
  "reachable": false,
  "pending": {"fields": ["state", "brightness"], "queued_at": 1790768304, "expires_at": 1790854704},
  "last_applied": null
}
```

Once the bulb returns, `pending` goes back to `null` and `last_applied` records
the write.

## Availability Topic

**Topic:** `wiz2mqtt/<bulb>/availability`

Payload values are `online` and `offline`. `offline` means a fault: the bulb
must answer and does not. A bulb whose power source is believed `off` stays
`online`.

The framework-owned `wiz2mqtt/status` heartbeat reports each bulb and power source as
`ok`, `error` or `stale`. A bulb turns `stale` only when its heartbeat tick keeps
failing past its 300 s freshness bound; it then goes `offline` and the app keeps
running. An unreachable bulb is not stale. See
[Health and recovery](configuration.md#health-and-recovery).

wiz2mqtt publishes immediately when a bulb push update arrives, and it also runs
a 60-second heartbeat tick so a bulb that has gone silent still gets a
liveness check.

wiz2mqtt subscribes to each `set` topic and to the optional `signal_topic` of
each power source (see [Power Source Signal Topic](#power-source-signal-topic)).
The push wake is in-process, so there is no trigger topic to publish to; see
[configuration.md](configuration.md) for the heartbeat and push-staleness
values.

## Power Source State Topic

**Topic:** `wiz2mqtt/<source>/state` (retained), one per `[[power_sources]]` entry.

```json
{"powered": "off", "power_request": "on", "members": ["kitchen", "living-room"]}
```

| Key | Values | Meaning |
| --- | ------ | ------- |
| `powered` | `"on"`, `"off"`, `"unknown"` | The belief about the circuit (ADR-007) |
| `power_request` | `"on"`, `"off"`, `null` | The desired power of the circuit; `null` means no request (ADR-009) |
| `members` | list of bulb names | The member bulbs, sorted |

wiz2mqtt accepts no command on this topic. A consumer maps `power_request` to
its relay.

## Power Source Signal Topic

**Topic:** the `signal_topic` of a `[[power_sources]]` entry (input only).

The relay owns this retained topic. wiz2mqtt subscribes to it and never
publishes to it. It accepts only the lowercase payloads `on` and `off`, after
one whitespace trim. It ignores and logs any other payload by source name, and
the ignored payload never appears in the log. An empty payload, for example a
cleared retained message, keeps the last known signal.

A `signal_topic` must not equal the topic prefix or lie below it. See
[configuration.md](configuration.md#power-sources) for the belief rules and the
broker access rules.

---

## Home Assistant Discovery Topics

When `app.discovery()` runs (first MQTT connect), wiz2mqtt publishes one retained,
QoS 1 config payload per entity. All of them point back at the `state` and `set`
topics above.

| Discovery topic | Component | `state_topic` | `command_topic` |
| --------------- | --------- | ------------- | --------------- |
| `homeassistant/light/wiz2mqtt/{bulb}_light/config` | `light` (`schema: json`) | `wiz2mqtt/{bulb}/state` | `wiz2mqtt/{bulb}/set` |
| `homeassistant/number/wiz2mqtt/{bulb}_effect_speed/config` | `number` | `wiz2mqtt/{bulb}/state` | `wiz2mqtt/{bulb}/set` |
| `homeassistant/sensor/wiz2mqtt/{bulb}_power/config` | `sensor` | `wiz2mqtt/{bulb}/state` | — (read-only) |
| `homeassistant/binary_sensor/wiz2mqtt/{bulb}_reachable/config` | `binary_sensor` (`device_class: connectivity`, diagnostic) | `wiz2mqtt/{bulb}/state` | — (read-only) |
| `homeassistant/sensor/wiz2mqtt/{bulb}_pending/config` | `sensor` (diagnostic): queued fields, or `none` | `wiz2mqtt/{bulb}/state` | — (read-only) |
| `homeassistant/sensor/wiz2mqtt/{bulb}_last_applied/config` | `sensor` (diagnostic): `confirmed`, `unconfirmed` or `none` | `wiz2mqtt/{bulb}/state` | — (read-only) |
| `homeassistant/binary_sensor/wiz2mqtt/{source}_powered/config` | `binary_sensor` (`device_class: power`) | `wiz2mqtt/{source}/state` | — (read-only) |
| `homeassistant/binary_sensor/wiz2mqtt/{source}_power_request/config` | `binary_sensor` (`entity_category: diagnostic`) | `wiz2mqtt/{source}/state` | — (read-only) |
| `homeassistant/binary_sensor/wiz2mqtt/bridge/config` | `binary_sensor` | `wiz2mqtt/status` | — |

The `light` payload carries `brightness: true` plus the colour metadata for the
bulb: `supported_color_modes`, `effect`/`effect_list`, and
`min_kelvin`/`max_kelvin`. These are **narrowed to each bulb's detected
capabilities** once wiz2mqtt has contacted it and been restarted — until then (a
first run, or a just-swapped bulb) the payload advertises the safe superset
`supported_color_modes: ["color_temp", "rgb"]`, `effect: true` with the full
38-scene `effect_list`, and `min_kelvin`/`max_kelvin` `2200`/`6500`. The `number`
payload uses `min` 10, `max` 200, `step` 1, `command_template`
`{"effect_speed": {{ value }}}`. The `sensor` payload is `device_class: power`,
`unit_of_measurement: W`, `state_class: measurement`.

## Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
this reference expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless wiz2mqtt refreshes it. wiz2mqtt re-publishes each retained topic with an
unchanged payload every third of that interval (8 hours by default). Non-retained
topics, such as the `error` topics and the `set` topics, carry no expiry. See
[MQTT 5 retained-message expiry](configuration.md#mqtt-5-retained-message-expiry) for the
operator contract and the MQTT 3.1.1 fallback.

## openHAB Generic MQTT Thing

`task wiz2mqtt:schema:openhab` renders — offline, from `docs/schema.yaml` — a
`Thing mqtt:topic:broker:wiz2mqtt_{bulb}` plus a matching Items file. A state
channel reads the bulb's state topic and a `_cmd` channel writes its `/set`
topic:

| Channel | Type | Wiring |
| ------- | ---- | ------ |
| `state` / `state_cmd` | `switch`, `on="ON"` `off="OFF"` | read `JSONPATH:$.state`; write `{"state":"%s"}` |
| `brightness` / `brightness_cmd` | `dimmer`, `min` 0 `max` 255 `step` 1 | read `JSONPATH:$.brightness`; write `{"brightness":%s}` |
| `hsb` / `hsb_cmd` | `color`, `colorMode="HSB"` | read `JSONPATH:$.hsb`; write `{"hsb":"%1$d,%2$d,%3$d"}` |
| `color_temp` / `color_temp_cmd` | `number`, `min` 2200 `max` 6500 `step` 1, Item label in K | read `JSONPATH:$.color_temp`; write `{"color_temp":%s}` |
| `effect` / `effect_cmd` | `string`; the command lists the WiZ scenes as `allowedStates` | read `JSONPATH:$.effect`; write `{"effect":"%s"}` |
| `effect_speed` / `effect_speed_cmd` | `number`, `min` 10 `max` 200 `step` 1 | read `JSONPATH:$.effect_speed`; write `{"effect_speed":%s}` |
| `power_draw_w` | `number`, read-only, Item label in W | read `JSONPATH:$.power_draw_w` |
| `reachable` | `switch`, read-only, `on="true"` `off="false"` | read `JSONPATH:$.reachable` |
| `pending` | `string`, read-only, `nullValue="NULL"` | read `JSONPATH:$[?(@.pending != null)].pending` (the JSON object) |
| `last_applied` | `string`, read-only, `nullValue="NULL"` | read `JSONPATH:$[?(@.last_applied != null)].last_applied` (the JSON object) |

`hsb`, `color_temp` and `effect` are only present in the colour mode that
uses them, so openHAB logs a JSONPATH warning for the other two on each state
message. The Item keeps its last value.

The deployment generator (`wiz2mqtt-openhab`, see
[openHAB generation](configuration.md#openhab-generation)) adds read-only
diagnostic channels:

| Thing | Channel | Wiring |
| ----- | ----- | ------ |
| Every bulb | `error` | `string`, `wiz2mqtt/{bulb}/error`, `JSONPATH:$.error_type` |
| Power source | `powered` | `JSONPATH:$[?(@.powered != null)].powered`, `on="on"`, `off="off"`, `nullValue="unknown"` |
| Power source | `power_request` | `JSONPATH:$[?(@.power_request != null)].power_request`, `on="on"`, `off="off"`, `nullValue="NULL"` |
| Bulb in a power source | `powered` | `JSONPATH:$[?(@.powered != null)].powered`, `on="true"`, `off="false"`, `nullValue="NULL"` |

The filter form of the JSONPATH turns a JSON `null` into the string `NULL`. A
plain `$.powered` would make openHAB discard the message and keep a stale value.
`nullValue` on a switch channel needs openHAB 5.1 or later.

cosalette publishes a JSON object on `wiz2mqtt/{bulb}/error` for each failure
of that bulb, for example a rejected `/set` payload (`invalid_command`). The
topic is not retained, so the `Error` Item is `NULL` after a restart and then
holds the `error_type` of the last failure. It is never cleared. Trigger rules
on `received update`, not on `changed`, to see a repeat of the same error.

| `error_type` | Meaning |
| ------------ | ------- |
| `invalid_command` | The `/set` payload was rejected; nothing is queued |
| `timeout_queued` | A `/set` write timed out. The command is queued and is applied when the bulb answers again (ADR-008) |
| `wiz_connection` | A `/set` write could not connect. The command is queued like a timeout |
| `wiz_identity` | The bulb at the configured IP reported another MAC; nothing is queued |
| `wiz_unsupported_command` | The bulb cannot do what the command asks; nothing is queued |
| `restore_unconfirmed` | The return path wrote three times and no read-back confirmed it. wiz2mqtt retains the desired state and retries only up to `restore_retry_limit` exhausted cycles, paced by `restore_retry_delays`. The terminal error carries `terminal: true`; a new `/set` starts a fresh budget. A write the bulb cannot express ends the cycle at once with one `WizUnsupportedCommandError` attempt and `terminal: true`. The object also carries `attempts`, `retry_cycles`, the reported `state` and `attempt_results`: one entry per attempt, `mismatch` or the exception class name such as `WizTimeoutError` |

A direct `/set` timeout published `wiz_timeout` before the switched-relay
safeguards; it now publishes `timeout_queued`. Update a rule that matched
`wiz_timeout`.

The `*_cmd` channels wrap the outbound scalar back into JSON with
`formatBeforePublish` (full Java `String.format`) so a single `.../set` payload
carries just the changed field.

**Availability.** Each Thing declares the `availabilityTopic` of its bulb
(`payloadAvailable="online"`, `payloadNotAvailable="offline"`). If the bulb publishes
`offline`, openHAB shows the Thing as OFFLINE. Regenerate your Things after you
upgrade to get this wiring.

**On and off.** openHAB runs a channel's `on`/`off` value through
`formatBeforePublish` too, so the `switch` declares the bare `on="ON"`
`off="OFF"` and publishes `{"state":"OFF"}`. The `dimmer` and `color` channels
declare no `on`/`off`: openHAB turns OFF into brightness 0
(`{"brightness":0}`, `{"hsb":"h,s,0"}`), and wiz2mqtt treats
[brightness 0 as OFF](#brightness-0-means-off). ON on a Dimmer is 100 %
(`{"brightness":255}`), and on a Color channel it restores the last colour.
Regenerate Things made before this release: their JSON `on`/`off` values were
wrapped a second time and rejected. Also regenerate Things made with wiz2mqtt
0.2.8 or earlier: their HSB command channel used only the hue and rejected every
colour command.

**Hue range.** openHAB's `Color`/HSB type uses hue `0..359`; the Home Assistant
JSON `color` object uses `0..360`. wiz2mqtt does **no** conversion — the one-unit
difference is a documented consumer-side concern, not a wire-format one. The
canonical internal colour model is `(hue, saturation, dimming)`; the `hsb` string
key (`"h,s,b"`) exists purely for openHAB and is ignored by Home Assistant.

---

## Framework Topics

Alongside the wiz2mqtt-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on — no setting disables them — retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `wiz2mqtt/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `wiz2mqtt/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`wiz2mqtt/_meta/registry`)

The canonical AsyncAPI document describing every channel wiz2mqtt publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`wiz2mqtt/_meta/state_model_drift`)

A machine-readable snapshot of `state_model` declaration drift (ADR-069): a handler
whose `state_model=` argument disagrees with its return type annotation. The topic is
published even when there is no drift — a clean app publishes `drift_count: 0` rather
than omitting the topic, so "no drift" is distinguishable from "never ran a version
that publishes this topic".

```json
{
  "schema_version": 1,
  "drift_count": 0,
  "entries": []
}
```

| Field                            | Type    | Description                                                      |
| ---------------------------------- | ------- | ------------------------------------------------------------------ |
| `schema_version`                 | integer | Envelope version; bumped only on an incompatible payload change    |
| `drift_count`                    | integer | Number of handlers with a declaration/annotation conflict          |
| `entries[].handler`              | string  | Registered handler name                                            |
| `entries[].archetype`            | string  | `"telemetry"` or `"command"`                                       |
| `entries[].kind`                 | string  | Drift kind — currently only `"annotation_conflict"`               |
| `entries[].declared_model`       | string  | The `state_model=` class name declared on the handler              |
| `entries[].effective_annotation` | string  | The handler's actual return type annotation                        |

!!! tip "Fleet-wide scraping"
    One subscription across a whole broker distinguishes a healthy app from one
    that predates this topic:

    ```bash
    mosquitto_sub -t '+/_meta/state_model_drift'
    ```

    An app publishing `drift_count: 0` is healthy. An app with no retained message
    on this topic at all has not been upgraded past cosalette 0.9.0.

### ACL guidance

Both topics disclose handler names, channel addresses, and payload schemas. If you
run a production broker ACL file, protect `_meta/#` the same way you protect
`_meta/registry`. Every `mosquitto.conf` shipped in this repo is
dev-only (`allow_anonymous true`, no ACL file), so there is nothing to change
in-repo — this note only applies if you deploy your own broker ACLs.
