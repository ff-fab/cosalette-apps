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
| `velux2mqtt/blind/state`                  | outbound | Position JSON                    | yes    | 1   |
| `velux2mqtt/blind/set`                    | inbound  | Cover command                    | ---    | --- |
| `velux2mqtt/blind/calibrate/state`        | outbound | Calibration state JSON           | yes    | 1   |
| `velux2mqtt/blind/calibrate/result`       | outbound | Calibration result JSON          | yes    | 1   |
| `velux2mqtt/blind/availability`           | outbound | `"online"` / `"offline"`         | yes    | 1   |
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

**Topic:** `velux2mqtt/{cover}/set`

Calibration commands are JSON payloads with a `"calibrate"` key, sent to the same
`/set` topic as normal cover commands. During active calibration, normal cover commands
are blocked.

```json title="Start calibration"
{"calibrate": "start"}
```

```json title="Start with options"
{"calibrate": "start", "runs": 5, "measure_offset": true, "measure_dead_band": true, "starting_state": "closed"}
```

```json title="Trigger button press"
{"calibrate": "go"}
```

```json title="Mark timing event"
{"calibrate": "mark"}
```

```json title="Cancel calibration"
{"calibrate": "cancel"}
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
