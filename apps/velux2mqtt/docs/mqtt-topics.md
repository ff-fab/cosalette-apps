# MQTT Topics

velux2mqtt publishes cover position state, calibration progress, health information, and
errors to a set of MQTT topics under the `velux2mqtt/` prefix. Each cover is a separate
device with its own command and state topics.

---

## Topic Overview

Each cover (e.g. `blind`, `window`) gets its own set of topics. The table below uses
`blind` as an example.

| Topic                                     | Dir      | Payload                          | Retain | QoS |
| ----------------------------------------- | -------- | -------------------------------- | ------ | --- |
| `velux2mqtt/blind/state`                       | outbound | Position JSON                    | yes    | 1   |
| `velux2mqtt/blind/set`                         | inbound  | Cover command                    | ---    | --- |
| `velux2mqtt/blind/calibrate/set`               | inbound  | Calibration command              | ---    | --- |
| `velux2mqtt/blind/calibrate/state`             | outbound | Calibration state JSON           | yes    | 1   |
| `velux2mqtt/blind/calibrate/result`            | outbound | Calibration result JSON          | yes    | 1   |
| `velux2mqtt/blind/calibrate/availability`      | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `velux2mqtt/blind/availability`                | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `velux2mqtt/blind/error`                  | outbound | Error JSON                       | no     | 1   |
| `velux2mqtt/status`                       | outbound | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `velux2mqtt/error`                        | outbound | Error JSON                       | no     | 1   |

---

## Payload Schemas

### Cover Position

**Topic:** `velux2mqtt/{cover}/state`

Published after every movement completes and on startup (after homing, if enabled).

```json
{
  "position": 75
}
```

| Field      | Type    | Description                                               |
| ---------- | ------- | --------------------------------------------------------- |
| `position` | integer | Current estimated position (0 = fully closed, 100 = fully open) |

Position is estimated from travel time --- there is no physical feedback sensor. See
[Architecture](architecture.md) for how the position tracker works.

### Cover Commands

**Topic:** `velux2mqtt/{cover}/set`

Accepts multiple command formats for compatibility with Home Assistant and manual MQTT
clients.

=== "Text commands"

    Simple directional commands (case-insensitive):

    ```text
    open       # move to 100% (up)
    up         # move to 100% (up)
    close      # move to 0% (down)
    down       # move to 0% (down)
    stop       # stop immediately
    ```

=== "Numeric"

    A bare integer (0--100) sets the target position:

    ```text
    42         # move to 42%
    0          # fully close
    100        # fully open
    ```

=== "JSON position"

    ```json
    {"position": 42}
    ```

=== "JSON command"

    ```json
    {"command": "open"}
    ```

### Calibration State

**Topic:** `velux2mqtt/{cover}/calibrate/state`

Published after every calibration action. Tracks the state machine progress so external
UIs can display calibration status.

```json title="During calibration"
{
  "state": "TIMING",
  "run": 2,
  "total_runs": 3,
  "direction": "OPEN"
}
```

```json title="Idle"
{
  "state": "IDLE"
}
```

| Field        | Type    | Description                                                       |
| ------------ | ------- | ----------------------------------------------------------------- |
| `state`      | string  | Current state: `IDLE`, `READY`, `TIMING_OFFSET`, `TIMING_DEAD_BAND`, `TIMING`, `COMPLETE` |
| `run`        | integer | Current run number (1-based), absent when IDLE                    |
| `total_runs` | integer | Total configured runs, absent when IDLE                           |
| `direction`  | string  | `CLOSE` or `OPEN`, absent when IDLE                               |

### Calibration Result

**Topic:** `velux2mqtt/{cover}/calibrate/result`

Published once when calibration completes. Contains the averaged measurements that should
be transferred to the cover configuration.

```json title="Basic (travel only)"
{
  "avg_close": 22.15,
  "avg_open": 24.03
}
```

```json title="With offset and dead band"
{
  "avg_close": 22.15,
  "avg_open": 24.03,
  "avg_offset": 0.82,
  "avg_dead_band": 1.35,
  "dead_band_pct": 5.6
}
```

| Field            | Type  | Description                                          |
| ---------------- | ----- | ---------------------------------------------------- |
| `avg_close`      | float | Average close (down) travel duration in seconds      |
| `avg_open`       | float | Average open (up) travel duration in seconds         |
| `avg_offset`     | float | Average motor start lag in seconds (if measured)     |
| `avg_dead_band`  | float | Average dead band (handle rotation) time (if measured) |
| `dead_band_pct`  | float | Dead band as percentage of total travel (if measured) |

### Calibration Commands

**Topic:** `velux2mqtt/{cover}/calibrate/set`

Calibration commands are JSON payloads with a `"phase"` key, sent to the dedicated
`/calibrate/set` sub-topic. During active calibration, normal cover commands (on
`{cover}/set`) are blocked. The `calibrate/availability` topic is published `"online"`
while calibration is active and `"offline"` otherwise.

```json title="Start calibration"
{"phase": "start"}
```

```json title="Start with options"
{"phase": "start", "runs": 5, "measure_offset": true, "measure_dead_band": true, "starting_state": "closed"}
```

```json title="Trigger button press"
{"phase": "go"}
```

```json title="Mark timing event"
{"phase": "mark"}
```

```json title="Cancel calibration"
{"phase": "cancel"}
```

| Action   | Description                                                         |
| -------- | ------------------------------------------------------------------- |
| `start`  | Begin calibration (optional: `runs`, `measure_offset`, `measure_dead_band`, `starting_state`) |
| `go`     | Press the direction button and start timing                         |
| `mark`   | Record a timing mark (offset, dead band, or travel depending on state) |
| `cancel` | Abort calibration and return to normal operation                    |

See [Calibration](calibration.md) for the full step-by-step procedure.

### Availability

**Topics:** `velux2mqtt/{cover}/availability`

Each cover device publishes its availability status. The cosalette framework manages
these automatically.

```text
"online"     # device is running
"offline"    # device has stopped (or app shutting down)
```

### Status (Heartbeat)

**Topic:** `velux2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last
Will and Testament (LWT) --- the broker publishes `"offline"` if velux2mqtt disconnects
unexpectedly.

```json title="Heartbeat"
{
  "status": "online",
  "uptime": 3600.0,
  "version": "0.0.0",
  "devices": {
    "blind": { "status": "online" },
    "window": { "status": "online" }
  }
}
```

### Error

**Topic:** `velux2mqtt/error`

Published (not retained) when a device encounters an error. The cosalette framework
deduplicates consecutive identical errors.

```json
{
  "type": "OSError",
  "message": "GPIO access failed",
  "device": "blind",
  "timestamp": 1700000000.0
}
```

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `velux2mqtt/{cover}/error` (e.g., `velux2mqtt/blind/error`). These have the same
    payload format.

---

## Framework Topics

Alongside the velux2mqtt-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on -- no setting disables them -- retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `velux2mqtt/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `velux2mqtt/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`velux2mqtt/_meta/registry`)

The canonical AsyncAPI document describing every channel velux2mqtt publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`velux2mqtt/_meta/state_model_drift`)

A machine-readable snapshot of `state_model` declaration drift (ADR-069): a handler
whose `state_model=` argument disagrees with its return type annotation. The topic is
published even when there is no drift -- a clean app publishes `drift_count: 0` rather
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
| `entries[].kind`                 | string  | Drift kind -- currently only `"annotation_conflict"`               |
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
`_meta/registry` -- see
[ADR-006](https://ff-fab.github.io/cosalette-apps/adr/ADR-006-mqtt-transport-security-posture/)
for this repo's transport posture. Every `mosquitto.conf` shipped in this repo is
dev-only (`allow_anonymous true`, no ACL file), so there is nothing to change
in-repo -- this note only applies if you deploy your own broker ACLs.

---

## Topic Naming Convention

velux2mqtt follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment   | Value                                                    |
| --------- | -------------------------------------------------------- |
| `prefix`  | App name --- `velux2mqtt` by default                     |
| `device`  | Cover name from configuration: `blind`, `window`, etc.   |
| `channel` | `state`, `set`, `availability`, `error`, or `calibrate/*` |

Global topics (`status`, `error`) omit the device segment:

```text
velux2mqtt/status
velux2mqtt/error
```

The topic prefix can be changed via `VELUX2MQTT_MQTT__TOPIC_PREFIX`.
