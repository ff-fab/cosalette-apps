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
characteristic. The payload shape is identical either way. Two read-health fields
follow the readings: when the read happened and how strongly the sensor was heard.

```json
{
  "temperature": 21.5,
  "humidity": 45.0,
  "radon_24h_avg": 42,
  "radon_long_term_avg": 38,
  "last_read": "2026-10-01T18:34:58.123456Z",
  "rssi": -71
}
```

| Field                | Type            | Unit   | Description                                  |
| -------------------- | --------------- | ------ | -------------------------------------------- |
| `temperature`        | float           | C      | Ambient temperature in degrees Celsius       |
| `humidity`           | float           | %      | Relative humidity as a percentage            |
| `radon_24h_avg`      | integer \| null | Bq/m3  | 24-hour rolling average radon concentration  |
| `radon_long_term_avg`| integer \| null | Bq/m3  | Long-term average radon concentration        |
| `last_read`          | string          | —      | ISO 8601 UTC time of the successful BLE read |
| `rssi`               | integer \| null | dBm    | Signal strength of the sensor's advertisement |

`last_read` lets a consumer see a value's age without tracking publication time:
the retained payload keeps the time of its own read, so an old `last_read` exposes a
stale reading even after a broker or consumer restart. `rssi` is taken from the
advertisement that the pre-connect scan observed; record it to spot a weakening link
(range, battery, obstruction) before reads start failing. It is `null` only when the
reader has no advertisement to report.

Both `last_read` and `rssi` are always included in published state. Their model defaults
can make them optional in the generated validation schema; that does not mean the app
omits them from runtime payloads.

Both fields are discovered as diagnostic entities: in Home Assistant as a `timestamp`
sensor and a `signal_strength` sensor (dBm); in openHAB (`cosalette schema openhab`) as a
`DateTime` item on a `datetime` channel and a `Number` item.

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
BLE failures are retried first; `"offline"` is published when those failures exhaust
the configured retry budget. A later successful read publishes `"online"` again.

Retryable failures are connection errors (including a sensor that is not found because
it stopped advertising or is out of range, a BlueZ D-Bus error, or a powered-off
adapter) and timeouts. A non-retryable `BleReadError` (a missing GATT characteristic or a
malformed frame) is not retried — a re-read would fail the same way — but it publishes
an error and marks the sensor `"offline"` straight away, because consumers are left
without a fresh reading either way.

Independently, a freshness watchdog tracks successful telemetry cycles and publishes
`"offline"` when none has completed for `stale_after` seconds. That catches what the
failure path cannot see, such as a stalled task or an unexpected handler error. The bound
is derived from the settings: two poll intervals plus the worst-case retry budget
(`2 × POLL_INTERVAL + 4 × POLL_TIMEOUT + 3 × 72 s`), which is 3696 s (about 62 minutes)
with the defaults. The next successful cycle clears every mark.

```text
"online"     # no availability source currently marks the entity offline
"offline"    # terminal read failure, stale telemetry, or a stopped task/app
```

See [Troubleshooting](troubleshooting.md) for what to do when the sensor stays offline.

This is the telemetry entity's availability, not a continuous Bluetooth adapter health
check. For example, it does not promise that the adapter or sensor remains reachable
between polls.

!!! warning "Availability alone does not prove the reading is fresh"

    The last good reading stays retained on `airthings2mqtt/airthings/state`, and
    the framework freshness watchdog turns availability `"offline"` after the
    derived window: two poll intervals plus the retry/timeout/backoff budget
    (about 62 minutes with the defaults). Stalled telemetry therefore becomes stale
    even while the health reporter runs. Arrival or publication age is not a reliable
    reading-age check: a broker can replay a retained payload on reconnect, and MQTT 5
    refreshes retained payloads unchanged every eight hours. Compare the payload's
    `last_read` with the current time as the authoritative reading-age check. A rule or
    alert threshold of about one hour is a reasonable default.

    - **openHAB:** `expire` metadata is a supplementary absence-of-updates guard, not a
      reliable reading-age check after reconnects or unchanged retained refreshes. Keep
      it if useful, and add a rule or alert comparing the `DateTime` `last_read` item
      with the current time. For example, the item can also expire to `UNDEF` if no
      update arrives; with the default 25-minute poll interval:

        ```text
        Number Airthings2Mqtt_Airthings_Radon24HAvg "Radon (24h avg) [%s Bq/m³]" {
            channel="mqtt:topic:broker:airthings2mqtt_airthings:radon_24h_avg",
            expire="1h,state=UNDEF"
        }
        ```

    - **Any consumer:** compare `last_read` against the clock rather than relying on the
      last publication time. Also monitor
      `devices.airthings.status` and heartbeat recency in
      [`airthings2mqtt/status`](#status-heartbeat), but do not use them as the
      only publication-age signal: freshness tracks successful handler cycles,
      which can differ from publication time.

### Status (Heartbeat)

**Topic:** `airthings2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last Will
and Testament (LWT) --- the broker publishes `"offline"` if airthings2mqtt disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime_s": 3600,
  "devices": {
    "airthings": {
      "status": "ok",
      "last_success_at": "2026-10-01T18:34:58+00:00",
      "consecutive_failures": 0,
      "last_error": null,
      "failing_since": null
    }
  },
  "version": "0.2.7"
}
```

| Field      | Type   | Description                                                                  |
| ---------- | ------ | ---------------------------------------------------------------------------- |
| `status`   | string | `"online"` or `"offline"`                                                    |
| `uptime_s` | integer | Seconds since application start                                             |
| `devices`  | object | Per-device status: `"ok"`, `"error"`, `"unavailable"`, `"circuit_open"` or `"stale"` |
| `version`  | string | Application version                                                          |

Telemetry entries include `last_success_at` (ISO 8601 string, or `null` before
the first success), `consecutive_failures` (integer), `last_error` (machine-readable
error type, or `null`) and `failing_since` (ISO 8601 string, or `null`). The last two
values are populated only during a failure streak and reset to `null` on recovery.
`"stale"` takes precedence over other device statuses while freshness is expired.
Untracked device and command entries omit these four fields.

### Error

**Topic:** `airthings2mqtt/error`

Published (not retained) when an error occurs. The cosalette framework deduplicates
consecutive errors of the same type: a persisting error is republished as a reminder (2nd, 4th, 8th, ... failure in the first hour, then hourly) carrying `details.count` and `details.first_seen`; count `1` marks a new incident.
BLE-specific errors (connection failures, read timeouts) are the most common.

```json
{
  "error_type": "ble_device_not_found",
  "message": "target not seen; 0 advertisers in 10s (no advertisements observed during scan)",
  "device": "airthings",
  "timestamp": "2026-10-01T18:34:58+00:00",
  "id": "c0ffee000001",
  "details": {"count": 1, "first_seen": "2026-10-01T18:34:58+00:00"}
}
```

| Field        | Type   | Description                                          |
| ------------ | ------ | ---------------------------------------------------- |
| `error_type` | string | Machine-readable error class (see below)             |
| `message`    | string | Human-readable error description                     |
| `device`     | string | Device that raised the error                         |
| `timestamp`  | string | ISO 8601 time when the error occurred                |
| `id`         | string | Correlation id, matching the local log line          |
| `details`    | object | `count` and `first_seen` of the current error streak |

| `error_type`           | Meaning                                                   | Retried |
| ---------------------- | --------------------------------------------------------- | ------- |
| `ble_device_not_found` | The target's advertisement was not observed during the scan\* | yes     |
| `ble_connection`       | Connection, BlueZ D-Bus or adapter failure                | yes     |
| `ble_timeout`          | A BLE connection or read timed out                        | yes     |
| `ble_read`             | A characteristic is missing or the frame cannot be decoded | no      |

\* Before each connect the app scans for the target's advertisement (at most 10 s, or a
quarter of `poll_timeout` if that is shorter). A miss reports how many distinct
advertiser addresses were observed: zero means no advertisements were observed during
that window; a non-zero count means other advertisements were observed but not the
target's. These observations can help narrow the investigation, but do not diagnose the
cause. Range, battery, advertising state, and another client are among the possibilities.

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `airthings2mqtt/airthings/error`. The payload format is the same.

---

## Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
the tables above expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless airthings2mqtt refreshes it. airthings2mqtt re-publishes each retained topic with an unchanged
payload every third of that interval (8 hours by default). For sensor state, this can
refresh delivery age without a new BLE reading; use `last_read` to judge reading age.
Non-retained topics, such as
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
