# Reference

Complete lookup reference — settings, MQTT topics, commands, CLI options,
error types, and API documentation.

---

## Settings Reference

All settings are read from environment variables prefixed with `JEELINK2MQTT_`.
A `.env` file in the working directory is loaded automatically.
Nested settings use `__` as delimiter (e.g. `JEELINK2MQTT_MQTT__HOST`).

### Application Settings

| Setting | Env Variable | Type | Default | Description |
|---------|-------------|------|---------|-------------|
| `serial_port` | `JEELINK2MQTT_SERIAL_PORT` | `str` | `/dev/ttyUSB0` | Serial port path (must start with `/dev/`) |
| `baud_rate` | `JEELINK2MQTT_BAUD_RATE` | `int` | `57600` | Serial baud rate |
| `sensors` | `JEELINK2MQTT_SENSORS` | `list[object]` | `[]` | Sensor definitions (JSON array) |
| `staleness_timeout_seconds` | `JEELINK2MQTT_STALENESS_TIMEOUT_SECONDS` | `float` | `600.0` | Global staleness timeout in seconds (min: 60) |
| `median_filter_window` | `JEELINK2MQTT_MEDIAN_FILTER_WINDOW` | `int` | `7` | Median filter window size (3–21, must be odd) |
| `heartbeat_interval_seconds` | `JEELINK2MQTT_HEARTBEAT_INTERVAL_SECONDS` | `float` | `180.0` | Heartbeat re-publish interval in seconds (min: 10) |

### Inherited cosalette Settings

| Setting | Env Variable | Type | Default | Description |
|---------|-------------|------|---------|-------------|
| `mqtt.host` | `JEELINK2MQTT_MQTT__HOST` | `str` | `localhost` | MQTT broker hostname |
| `mqtt.port` | `JEELINK2MQTT_MQTT__PORT` | `int` | `1883` | MQTT broker port |
| `mqtt.username` | `JEELINK2MQTT_MQTT__USERNAME` | `str` | `""` | MQTT username |
| `mqtt.password` | `JEELINK2MQTT_MQTT__PASSWORD` | `str` | `""` | MQTT password |
| `mqtt.protocol_version` | `JEELINK2MQTT_MQTT__PROTOCOL_VERSION` | `str` | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below |
| `mqtt.message_expiry_interval` | `JEELINK2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | `int` | `86400` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects jeelink2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): sensor state, availability, mapping snapshot, Home
Assistant discovery, `_meta/*` and the last will. While jeelink2mqtt runs, it
re-publishes each retained topic every third of that interval (default 8 hours), so the
topics stay alive. A topic that nothing refreshes any more, such as a renamed entity or
a stopped process, disappears from the broker by itself.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, jeelink2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `JEELINK2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If jeelink2mqtt is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics until the next publish.
- **Consumers see one repeat per refresh.** The repeat has the same payload as the last
  publish, and the broker forwards it to live subscribers without the retain flag, so it
  looks like a normal message. Home Assistant sensors do not change state on a repeat.
  `jeelink2mqtt/{sensor}/state` is already re-published every
  `HEARTBEAT_INTERVAL_SECONDS` (default 180 s), so its refresh is negligible.
  `jeelink2mqtt/mapping/state` is published only when a mapping changes, so its refresh
  is a real repeat. The repeat keeps the original `timestamp` and `last_seen`, so a
  freshness check on those fields is not fooled by a refresh.

### Validators

| Field | Constraint |
|-------|-----------|
| `serial_port` | Must start with `/dev/` |
| `median_filter_window` | Must be odd, between 3 and 21 |
| `staleness_timeout_seconds` | Minimum 60.0 |
| `heartbeat_interval_seconds` | Minimum 10.0 |

---

## Sensor Configuration Fields

Each entry in the `JEELINK2MQTT_SENSORS` JSON array supports:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | **Yes** | — | Logical sensor name (e.g. `"office"`, `"outdoor"`) |
| `temp_offset` | `float` | No | `0.0` | Calibration offset added to temperature (°C) |
| `humidity_offset` | `float` | No | `0.0` | Calibration offset added to humidity (percentage points) |
| `staleness_timeout` | `float \| null` | No | `null` | Per-sensor staleness override in seconds (`null` = use global) |

**Example:**

```env
JEELINK2MQTT_SENSORS='[
  {"name": "office", "temp_offset": -0.5, "humidity_offset": 2.0},
  {"name": "outdoor", "staleness_timeout": 900},
  {"name": "bedroom"}
]'
```

---

## MQTT Topic Map

!!! warning "`discoverable=False` is not access control"

    A channel marked `discoverable=False` is omitted from Home Assistant discovery
    output. It is **still subscribed and still acts on what it receives.** The flag
    changes what Home Assistant is told about, not who may publish. Anyone who can
    reach the broker can still drive these topics, and the bundled broker in
    `compose.yml` is plaintext with `allow_anonymous true`. Restrict
    access with broker ACLs and `<PREFIX>_MQTT__TLS=true`, not with this flag.

| Topic | Direction | Retained | Payload |
|-------|-----------|----------|---------|
| `jeelink2mqtt/{sensor}/state` | Out | Yes | `{temperature, humidity, low_battery, timestamp}` |
| `jeelink2mqtt/{sensor}/availability` | Out | Yes | `"online"` or `"offline"` |
| `jeelink2mqtt/raw/state` | Out | No | `{sensor_id, temperature, humidity, low_battery, timestamp}` |
| `jeelink2mqtt/mapping/state` | Out | Yes | `{sensor_name: {sensor_id, mapped_at, last_seen}}` |
| `jeelink2mqtt/mapping/event` | Out | No | `{event_type, sensor_name, old_sensor_id, new_sensor_id, timestamp, reason}` |
| `jeelink2mqtt/mapping/set` | In | No | `{command, ...params}` |

### Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
the tables above expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless jeelink2mqtt refreshes it. jeelink2mqtt re-publishes each retained topic with an unchanged
payload every third of that interval (8 hours by default). Non-retained topics, such as
the `error` topics, carry no expiry. See
[MQTT 5 retained-message expiry](#mqtt-5-retained-message-expiry) for the
operator contract and the MQTT 3.1.1 fallback.

### Sensor State Payload

```json
{
  "temperature": 21.3,
  "humidity": 52,
  "low_battery": false,
  "timestamp": "2026-03-04T10:15:00+00:00"
}
```

### Mapping Event Payload

```json
{
  "event_type": "auto_adopt",
  "sensor_name": "office",
  "old_sensor_id": null,
  "new_sensor_id": 42,
  "timestamp": "2026-03-04T10:15:00+00:00",
  "reason": "Auto-adopted sensor ID 42 for 'office'"
}
```

Event types: `auto_adopt`, `manual_assign`, `manual_reset`, `reset_all`.

### Framework Topics

Alongside the topics above, cosalette itself publishes two framework-owned topics.
Both are always on — no setting disables them — retained, QoS 1, and republished
byte-identically on every broker connect.

| Topic                                   | Payload                           | Retain | QoS |
| ----------------------------------------- | ---------------------------------- | ------ | --- |
| `jeelink2mqtt/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `jeelink2mqtt/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

#### Registry (`jeelink2mqtt/_meta/registry`)

The canonical AsyncAPI document describing every channel jeelink2mqtt publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

#### State Model Drift (`jeelink2mqtt/_meta/state_model_drift`)

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

#### ACL guidance

Both topics disclose handler names, channel addresses, and payload schemas. If you
run a production broker ACL file, protect `_meta/#` the same way you protect
`_meta/registry`. The `mosquitto.conf` shipped with jeelink2mqtt is
dev-only (`allow_anonymous true`, no ACL file), so there is nothing to change
in-repo — this note only applies if you deploy your own broker ACLs.

---

## Command Reference

Commands are sent as JSON to `jeelink2mqtt/mapping/set`.  Responses are
published to `jeelink2mqtt/mapping/state`.

| Command | Parameters | Description |
|---------|-----------|-------------|
| `assign` | `sensor_name` (str), `sensor_id` (int) | Manually assign an ephemeral ID to a logical sensor name |
| `reset` | `sensor_name` (str) | Remove the mapping for a single sensor |
| `reset_all` | *(none)* | Clear all sensor mappings |
| `list_unknown` | *(none)* | List recently-seen unmapped sensor IDs |

### `assign` Response

```json
{
  "status": "ok",
  "event": {
    "event_type": "manual_assign",
    "sensor_name": "office",
    "old_sensor_id": null,
    "new_sensor_id": 42,
    "reason": "Manually assigned sensor ID 42 to 'office'"
  }
}
```

### `reset` Response

```json
{
  "status": "ok",
  "event": {
    "event_type": "manual_reset",
    "sensor_name": "office",
    "old_sensor_id": 42
  }
}
```

### `reset_all` Response

```json
{
  "status": "ok",
  "cleared": 2,
  "sensors": ["office", "outdoor"]
}
```

### `list_unknown` Response

```json
{
  "status": "ok",
  "unknown_sensors": {
    "42": {
      "temperature": 21.3,
      "humidity": 55,
      "low_battery": false,
      "timestamp": "2026-03-04T10:15:00+00:00"
    }
  }
}
```

### Error Responses

```json
{"error": "Invalid JSON payload"}
{"error": "Unknown command: foo"}
{"error": "assign requires 'sensor_name' and 'sensor_id'"}
{"error": "Sensor ID 42 is already mapped to 'outdoor', cannot assign to 'office'"}
{"error": "Unknown sensor name 'foo' — must be one of the configured sensors"}
```

---

## CLI Options

jeelink2mqtt uses the cosalette CLI framework (Typer-based).  Available
flags:

| Flag | Description |
|------|-------------|
| `--dry-run` | Use fake adapter — no hardware required |
| `--version` | Print version and exit |
| `--log-level` | Set logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--env-file` | Path to `.env` file (default: `.env` in working directory) |

```bash
jeelink2mqtt --dry-run --log-level DEBUG --env-file /etc/jeelink2mqtt/.env
```

---

## Error Types

Domain exceptions are mapped to MQTT error type strings for structured
error reporting:

| Exception | MQTT Error Type | Description |
|-----------|----------------|-------------|
| `SerialConnectionError` | `serial_connection` | JeeLink serial port unavailable or disconnected |
| `FrameParseError` | `frame_parse` | Received data doesn't match LaCrosse frame format |
| `MappingConflictError` | `mapping_conflict` | ID already assigned to another sensor |
| `StalenessTimeoutError` | `staleness_timeout` | Sensor hasn't sent readings within the staleness window |
| `UnknownSensorError` | `unknown_sensor` | Reading from an unrecognised/unmapped sensor ID |

---

## API Reference

Auto-generated from source docstrings.

### Models

::: jeelink2mqtt.models
    options:
      heading_level: 4

### Settings

::: jeelink2mqtt.settings
    options:
      heading_level: 4

### Errors

::: jeelink2mqtt.errors
    options:
      heading_level: 4

### Ports

::: jeelink2mqtt.ports
    options:
      heading_level: 4

### Calibration

::: jeelink2mqtt.calibration
    options:
      heading_level: 4

### Filters

::: jeelink2mqtt.filters
    options:
      heading_level: 4
