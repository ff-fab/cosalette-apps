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
| `effect` | integer `1..1000` | WiZ scene/effect id |

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
`_meta/registry` — see
[ADR-006](https://ff-fab.github.io/cosalette-apps/adr/ADR-006-mqtt-transport-security-posture/)
for this repo's transport posture. Every `mosquitto.conf` shipped in this repo is
dev-only (`allow_anonymous true`, no ACL file), so there is nothing to change
in-repo — this note only applies if you deploy your own broker ACLs.
