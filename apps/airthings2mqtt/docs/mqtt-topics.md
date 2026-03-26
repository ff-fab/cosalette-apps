# MQTT Topics

airthings2mqtt publishes sensor state, health information, and errors to a set of MQTT
topics under the `airthings2mqtt/` prefix.

---

## Topic Overview

| Topic                                   | Dir      | Payload                          | Retain | QoS |
| --------------------------------------- | -------- | -------------------------------- | ------ | --- |
| `airthings2mqtt/airthings/state`        | outbound | Sensor reading JSON              | yes    | 1   |
| `airthings2mqtt/airthings/availability` | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `airthings2mqtt/airthings/error`        | outbound | Per-device error JSON            | no     | 1   |
| `airthings2mqtt/status`                 | outbound | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `airthings2mqtt/error`                  | outbound | Error JSON                       | no     | 1   |

---

## Payload Schemas

### Sensor State

**Topic:** `airthings2mqtt/airthings/state`

Published after each successful BLE poll. Contains all four sensor readings from the
Airthings Wave.

```json
{
  "temperature": 21.5,
  "humidity": 45.0,
  "radon_24h_avg": 42,
  "radon_long_term_avg": 38
}
```

| Field                | Type    | Unit   | Description                                  |
| -------------------- | ------- | ------ | -------------------------------------------- |
| `temperature`        | float   | C      | Ambient temperature in degrees Celsius       |
| `humidity`           | float   | %      | Relative humidity as a percentage            |
| `radon_24h_avg`      | integer | Bq/m3  | 24-hour rolling average radon concentration  |
| `radon_long_term_avg`| integer | Bq/m3  | Long-term average radon concentration        |

!!! info "Polling frequency"
    Airthings Wave sensors update their internal readings approximately every 5 minutes.
    The default polling interval is 1500 seconds (25 minutes), balancing data freshness
    with BLE battery and connection overhead. See [Configuration](configuration.md) to
    adjust.

### Availability

**Topic:** `airthings2mqtt/airthings/availability`

Managed automatically by the cosalette framework. Published when the device comes online
or goes offline.

```text
"online"     # device is running and reachable
"offline"    # device has stopped or is unreachable
```

### Status (Heartbeat)

**Topic:** `airthings2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last Will
and Testament (LWT) --- the broker publishes `"offline"` if airthings2mqtt disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime": 3600.0,
  "version": "0.1.0",
  "devices": {
    "airthings": { "status": "online" }
  }
}
```

| Field     | Type   | Description                                    |
| --------- | ------ | ---------------------------------------------- |
| `status`  | string | `"online"` or `"offline"`                      |
| `uptime`  | float  | Seconds since application start                |
| `version` | string | Application version                            |
| `devices` | object | Per-device status map                          |

### Error

**Topic:** `airthings2mqtt/error`

Published (not retained) when an error occurs. The cosalette framework deduplicates
consecutive identical errors. BLE-specific errors (connection failures, read timeouts)
are the most common.

```json
{
  "type": "BleConnectionError",
  "message": "Failed to connect to AA:BB:CC:DD:EE:FF",
  "device": "airthings",
  "timestamp": 1700000000.0
}
```

| Field       | Type   | Description                            |
| ----------- | ------ | -------------------------------------- |
| `type`      | string | Python exception class name            |
| `message`   | string | Human-readable error description       |
| `device`    | string | Device that raised the error           |
| `timestamp` | float  | Unix timestamp when the error occurred |

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `airthings2mqtt/airthings/error`. The payload format is the same.

---

## Topic Naming Convention

airthings2mqtt follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment   | Value                                                          |
| --------- | -------------------------------------------------------------- |
| `prefix`  | App name --- `airthings2mqtt` by default (configurable)        |
| `device`  | Device name: `airthings` (configurable via `device_name`)      |
| `channel` | `state`, `availability`, or `error`                            |

Global topics (`status`, `error`) omit the device segment:

```text
airthings2mqtt/status
airthings2mqtt/error
```

The topic prefix and device name are configurable. See [Configuration](configuration.md)
for details on `AIRTHINGS2MQTT_MQTT__TOPIC_PREFIX` and `AIRTHINGS2MQTT_DEVICE_NAME`.
