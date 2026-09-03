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
