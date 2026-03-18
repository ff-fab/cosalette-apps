# MQTT Topics

gas2mqtt publishes device state, health information, and errors to a set of MQTT topics
under the `gas2mqtt/` prefix. One topic accepts inbound commands.

---

## Topic Overview

| Topic                                | Dir      | Payload                          | Retain | QoS |
| ------------------------------------ | -------- | -------------------------------- | ------ | --- |
| `gas2mqtt/gas_counter/state`         | outbound | Gas counter JSON                 | yes    | 1   |
| `gas2mqtt/gas_counter/set`           | inbound  | Set consumption JSON             | —      | —   |
| `gas2mqtt/gas_counter/availability`  | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `gas2mqtt/temperature/state`         | outbound | Temperature JSON                 | yes    | 1   |
| `gas2mqtt/temperature/availability`  | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `gas2mqtt/magnetometer/state` ¹      | outbound | Raw magnetometer JSON            | yes    | 1   |
| `gas2mqtt/magnetometer/availability` ¹ | outbound | `"online"` / `"offline"`       | yes    | 1   |
| `gas2mqtt/status`                    | outbound | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `gas2mqtt/error`                     | outbound | Error JSON                       | no     | 1   |

¹ Only active when `GAS2MQTT_ENABLE_DEBUG_DEVICE=true`.

---

## Payload Schemas

### Gas Counter

**Topic:** `gas2mqtt/gas_counter/state`

Published on every trigger event (not every poll). Includes the optional
`consumption_m3` field when consumption tracking is enabled.

```json title="Basic"
{
  "counter": 42,
  "trigger": "CLOSED"
}
```

```json title="With consumption tracking"
{
  "counter": 42,
  "trigger": "CLOSED",
  "consumption_m3": 0.42
}
```

| Field             | Type     | Description                                |
| ----------------- | -------- | ------------------------------------------ |
| `counter`         | integer  | Cumulative tick count (wraps at 65536)     |
| `trigger`         | string   | `"OPEN"` or `"CLOSED"` — current trigger state |
| `consumption_m3`  | float    | Cumulative gas in m³ (optional)            |

### Temperature

**Topic:** `gas2mqtt/temperature/state`

Polled at the configured `temperature_interval` (default: every 5 minutes) but only
published when the PT1-filtered value changes by more than **0.05 °C** (cosalette
`OnChange` publish strategy). This suppresses duplicate readings when the temperature
is stable.

```json
{
  "temperature": 21.5
}
```

| Field         | Type   | Description                               |
| ------------- | ------ | ----------------------------------------- |
| `temperature` | float  | PT1-filtered temperature in °C           |

### Magnetometer (Debug)

**Topic:** `gas2mqtt/magnetometer/state`

Only published when `GAS2MQTT_ENABLE_DEBUG_DEVICE=true`. Published at `poll_interval`.

```json
{
  "bx": 123,
  "by": -456,
  "bz": -5000
}
```

| Field | Type    | Description                        |
| ----- | ------- | ---------------------------------- |
| `bx`  | integer | Magnetic field strength, X axis    |
| `by`  | integer | Magnetic field strength, Y axis    |
| `bz`  | integer | Magnetic field strength, Z axis    |

### Availability

**Topics:** `gas2mqtt/{device}/availability`

Each device publishes its availability status. The cosalette framework manages these
automatically.

```text
"online"     # device is running
"offline"    # device has stopped (or app shutting down)
```

### Status (Heartbeat)

**Topic:** `gas2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the
Last Will and Testament (LWT) — the broker publishes `"offline"` if gas2mqtt
disconnects unexpectedly.

```json title="Heartbeat"
{
  "status": "online",
  "uptime": 3600.0,
  "version": "1.0.0",
  "devices": {
    "gas_counter": { "status": "online" },
    "temperature": { "status": "online" },
    "magnetometer": { "status": "online" }
  }
}
```

### Error

**Topic:** `gas2mqtt/error`

Published (not retained) when a device encounters an error. The cosalette framework
deduplicates consecutive identical errors.

```json
{
  "type": "OSError",
  "message": "I2C bus read failed",
  "device": "gas_counter",
  "timestamp": 1700000000.0
}
```

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `gas2mqtt/{device}/error` (e.g., `gas2mqtt/gas_counter/error`). These have the same
    payload format.

---

## Inbound Commands

### Set Consumption

**Topic:** `gas2mqtt/gas_counter/set`

Set the cumulative consumption counter to an absolute value. Requires
`GAS2MQTT_ENABLE_CONSUMPTION_TRACKING=true`.

```json
{
  "consumption_m3": 12345.678
}
```

After receiving a valid command, gas2mqtt publishes an updated state to
`gas2mqtt/gas_counter/state`.

!!! warning "Consumption tracking must be enabled"
    Commands sent when `enable_consumption_tracking` is `false` are logged as warnings
    and ignored.

---

## Topic Naming Convention

gas2mqtt follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment    | Value                                                    |
| ---------- | -------------------------------------------------------- |
| `prefix`   | App name — `gas2mqtt` by default                         |
| `device`   | Device name: `gas_counter`, `temperature`, `magnetometer`|
| `channel`  | `state`, `set`, `availability`, or `error`               |

Global topics (`status`, `error`) omit the device segment:

```text
gas2mqtt/status
gas2mqtt/error
```
