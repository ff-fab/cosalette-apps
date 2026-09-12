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
| `brightness` | integer `1..255` | Home Assistant brightness scale |
| `color` | object `{r,g,b}` | RGB values `0..255` |
| `color_temp` | integer `1..10000` | Kelvin |
| `effect` | string | WiZ scene name (one of the advertised `effect_list`, e.g. `"Ocean"`) |

`color`, `color_temp`, and `effect` are mutually exclusive. Invalid combinations
are rejected before the adapter is called.

## State Topic

**Topic:** `wiz2mqtt/<bulb>/state`

The app publishes a retained JSON payload. `state` is always present; the other
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

## Availability Topic

**Topic:** `wiz2mqtt/<bulb>/availability`

Payload values are `online` and `offline`.

wiz2mqtt publishes immediately when a bulb push update arrives, and it also runs
a 60-second heartbeat tick so idle bulbs still get periodic liveness checks.

`set` is the only topic wiz2mqtt subscribes. The push wake is in-process, so
there is no trigger topic to publish to; see
[configuration.md](configuration.md) for the heartbeat and push-staleness
values.

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

Preview the exact payloads with `task wiz2mqtt:schema:ha-discovery` (the offline
path always emits the superset — it has no bulb to probe).

## openHAB Generic MQTT Thing

`task wiz2mqtt:schema:openhab` renders — offline, from `docs/schema.yaml` — a
`Thing mqtt:topic:broker:wiz2mqtt_{bulb}` plus a matching Items file. Two channel
sets are emitted per bulb:

| Channel | Type | Wiring |
| ------- | ---- | ------ |
| `state` / `state_cmd` | `switch` | read `JSONPATH:$.state`; write `{"state":"%s"}` |
| `brightness` / `brightness_cmd` | `dimmer`, `min` 1 `max` 255 `step` 1 | read `JSONPATH:$.brightness`; write `{"brightness":%s}` |
| `hsb` / `hsb_cmd` | `color`, `colorMode="HSB"` | read `JSONPATH:$.hsb`; write `{"hsb":"%s"}` |
| `effect` / `effect_cmd` | `string` | read `JSONPATH:$.effect`; write `{"effect":"%s"}` |

The `*_cmd` channels wrap the outbound scalar back into JSON with
`formatBeforePublish` (full Java `String.format`) so a single `.../set` payload
carries just the changed field.

**On/off bypasses `formatBeforePublish`.** The `dimmer`, `color`, and `switch`
channels also declare explicit `on`/`off` strings
(`on="{\"state\": \"ON\"}"`, `off="{\"state\": \"OFF\"}"`). openHAB sends those
verbatim without running `formatBeforePublish`, so an `OFF` command on the
brightness or colour channel emits a well-formed `{"state": "OFF"}` rather than
`{"brightness":OFF}`.

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
