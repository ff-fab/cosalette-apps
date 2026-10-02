# MQTT Topics

airthings2mqtt publishes sensor state, entity availability, and errors under the
configured MQTT topic prefix. The examples below use the defaults: prefix
`airthings2mqtt` and device name `airthings`.

---

## Topic Overview

| Topic                                   | Dir      | Payload                          | Retain | QoS |
| --------------------------------------- | -------- | -------------------------------- | ------ | --- |
| `airthings2mqtt/airthings/state`        | outbound | Sensor reading JSON              | yes    | 1   |
| `airthings2mqtt/airthings/set`          | inbound  | Empty payload                    | no     | 1   |
| `airthings2mqtt/airthings/availability` | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `airthings2mqtt/airthings/error`        | outbound | Per-device error JSON            | no     | 1   |
| `airthings2mqtt/status`                 | outbound | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `airthings2mqtt/error`                  | outbound | Error JSON                       | no     | 1   |

---

## Payload Schemas

### Sensor State

**Topic:** `airthings2mqtt/airthings/state`

Published after each successful BLE poll. Contains all four sensor readings from the
Airthings Wave, decoded from whichever GATT layout the unit uses — the 1st-gen
four-characteristic set or the Wave 2 / Wave Radon (2nd-gen) single "current values"
characteristic. The payload shape is identical either way.

```json
{
  "temperature": 21.5,
  "humidity": 45.0,
  "radon_24h_avg": 42,
  "radon_long_term_avg": 38
}
```

| Field                | Type            | Unit   | Description                                  |
| -------------------- | --------------- | ------ | -------------------------------------------- |
| `temperature`        | float           | C      | Ambient temperature in degrees Celsius       |
| `humidity`           | float           | %      | Relative humidity as a percentage            |
| `radon_24h_avg`      | integer \| null | Bq/m3  | 24-hour rolling average radon concentration  |
| `radon_long_term_avg`| integer \| null | Bq/m3  | Long-term average radon concentration        |

!!! note "Radon can be `null`"

    On a Wave 2 / Wave Radon unit, a radon value that decodes outside the plausible
    0–16383 Bq/m³ range (a garbled BLE frame) is published as JSON `null` rather than
    a false reading — the key is always present. The 1st-gen path always yields an
    integer.

!!! info "Polling frequency"
    Airthings Wave sensors update their internal readings approximately every 5 minutes.
    The default polling interval is 1500 seconds (25 minutes), balancing data freshness
    with BLE battery and connection overhead. See [Configuration](configuration.md) to
    adjust.

### On-Demand Re-read

**Topic:** `airthings2mqtt/airthings/set`

Publish an empty payload to trigger an immediate BLE re-read without waiting for the
next 25-minute polling interval.

```bash
mosquitto_pub -h localhost -t "airthings2mqtt/airthings/set" -n
```

The fresh reading is published to `airthings2mqtt/airthings/state` using the same schema
as scheduled polls.

!!! note "Re-reads are rate limited"

    Consecutive re-reads are spaced at least 30 seconds apart. A request that arrives
    inside that window is *delayed*, not dropped — the re-read still happens once the
    window reopens. This keeps a stuck automation or a held-down dashboard button from
    turning into a stream of BLE connections to a battery-powered sensor.

### Availability

**Topic:** `airthings2mqtt/airthings/availability`

Managed automatically by the cosalette framework and retained by the broker. Retryable
BLE failures are retried first; `"offline"` is published only when those failures exhaust
the configured retry budget. A later successful read publishes `"online"` again.

Retryable failures are connection errors (including a sensor that is not found because
it stopped advertising or is out of range, a BlueZ D-Bus error, or a powered-off
adapter) and timeouts. A non-retryable `BleReadError` (a missing GATT characteristic or a
malformed frame) publishes an error without retrying and leaves availability `"online"`,
because unreadable data does not necessarily mean the device is unreachable.

```text
"online"     # no retryable reachability failure has exhausted its retry budget
"offline"    # retryable failures exhausted the configured retry budget
```

This is the telemetry entity's availability, not a continuous Bluetooth adapter health
check. For example, it does not promise that the adapter or sensor remains reachable
between polls.

!!! warning "Availability alone does not prove the reading is fresh"

    The last good reading stays retained on `airthings2mqtt/airthings/state`, and
    availability only turns `"offline"` after a retryable failure exhausts its retries.
    A `BleReadError` that repeats every poll, or a bridge whose telemetry task has
    stopped, keeps availability `"online"` while the value goes stale. Guard the
    consumer as well, sized to about two poll intervals:

    - **openHAB:** add `expire` metadata to each item, so a value that is not refreshed
      becomes `UNDEF`. With the default 25-minute poll interval:

        ```text
        Number Airthings2Mqtt_Airthings_Radon24HAvg "Radon (24h avg) [%s Bq/m³]" {
            channel="mqtt:topic:broker:airthings2mqtt_airthings:radon_24h_avg",
            expire="1h,state=UNDEF"
        }
        ```

    - **Any consumer:** alert when the last publication to
      `airthings2mqtt/airthings/state` is older than about an hour. Also monitor
      `devices.airthings.status` and heartbeat recency in
      [`airthings2mqtt/status`](#status-heartbeat), but do not use them as the
      only freshness signal: the telemetry loop can stop while the health reporter
      remains healthy.

### Status (Heartbeat)

**Topic:** `airthings2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last Will
and Testament (LWT) --- the broker publishes `"offline"` if airthings2mqtt disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime_s": 3600.0,
  "devices": {
    "airthings": { "status": "ok" }
  },
  "version": "0.2.7"
}
```

| Field      | Type   | Description                                                                  |
| ---------- | ------ | ---------------------------------------------------------------------------- |
| `status`   | string | `"online"` or `"offline"`                                                    |
| `uptime_s` | float  | Seconds since application start                                              |
| `devices`  | object | Per-device status: `"ok"`, `"error"`, `"unavailable"` or `"circuit_open"`    |
| `version`  | string | Application version                                                          |

### Error

**Topic:** `airthings2mqtt/error`

Published (not retained) when an error occurs. The cosalette framework deduplicates
consecutive errors of the same type, so a persistent failure is reported once, at onset.
BLE-specific errors (connection failures, read timeouts) are the most common.

```json
{
  "error_type": "ble_device_not_found",
  "message": "BleakDeviceNotFoundError: Device with address **:EE:FF was not found.",
  "device": "airthings",
  "timestamp": "2026-10-01T18:34:58+00:00",
  "id": "c0ffee000001",
  "details": {}
}
```

| Field        | Type   | Description                                          |
| ------------ | ------ | ---------------------------------------------------- |
| `error_type` | string | Machine-readable error class (see below)             |
| `message`    | string | Human-readable error description                     |
| `device`     | string | Device that raised the error                         |
| `timestamp`  | string | ISO 8601 time when the error occurred                |
| `id`         | string | Correlation id, matching the local log line          |
| `details`    | object | Additional context (usually empty)                   |

| `error_type`           | Meaning                                                   | Retried |
| ---------------------- | --------------------------------------------------------- | ------- |
| `ble_device_not_found` | The adapter did not see the sensor (not advertising)      | yes     |
| `ble_connection`       | Connection, BlueZ D-Bus or adapter failure                | yes     |
| `ble_timeout`          | A BLE connection or read timed out                        | yes     |
| `ble_read`             | A characteristic is missing or the frame cannot be decoded | no      |

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `airthings2mqtt/airthings/error`. The payload format is the same.

---

## Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
the tables above expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless airthings2mqtt refreshes it. airthings2mqtt re-publishes each retained topic with an unchanged
payload every third of that interval (8 hours by default). Non-retained topics, such as
`airthings2mqtt/error`, carry no expiry. See
[MQTT 5 retained-message expiry](configuration.md#mqtt-5-retained-message-expiry) for the
operator contract and the MQTT 3.1.1 fallback.

---

## Framework Topics

Alongside the airthings2mqtt-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on — no setting disables them — retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `airthings2mqtt/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `airthings2mqtt/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`airthings2mqtt/_meta/registry`)

The canonical AsyncAPI document describing every channel airthings2mqtt publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`airthings2mqtt/_meta/state_model_drift`)

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

---

## Topic Naming Convention

airthings2mqtt follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment   | Value                                                          |
| --------- | -------------------------------------------------------------- |
| `prefix`  | App name --- `airthings2mqtt` by default (configurable)        |
| `device`  | `AIRTHINGS2MQTT_DEVICE_NAME` --- `airthings` by default        |
| `channel` | `state`, `set`, `error`, or `availability`                     |

Global topics (`status`, `error`) omit the device segment:

```text
airthings2mqtt/status
airthings2mqtt/error
```

The four entity topics are therefore
`{prefix}/{device_name}/{state,set,error,availability}`. Changing
`AIRTHINGS2MQTT_DEVICE_NAME` changes all four; changing
`AIRTHINGS2MQTT_MQTT__TOPIC_PREFIX` changes their root prefix as well as the global and
framework-owned topics. See [Configuration](configuration.md) for both settings.
