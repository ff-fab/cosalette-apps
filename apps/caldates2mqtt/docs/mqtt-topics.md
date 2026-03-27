# MQTT Topics

caldates2mqtt publishes calendar event data, health information, and errors to a set of
MQTT topics under the `caldates2mqtt/` prefix. Each configured calendar gets its own
device topics.

---

## Topic Overview

| Topic                                    | Dir      | Payload                          | Retain | QoS |
| ---------------------------------------- | -------- | -------------------------------- | ------ | --- |
| `caldates2mqtt/{calendar}/state`         | outbound | Calendar events JSON             | yes    | 1   |
| `caldates2mqtt/{calendar}/set`           | inbound  | Re-read command (JSON or empty)  | ---    | --- |
| `caldates2mqtt/{calendar}/availability`  | outbound | `"online"` / `"offline"`         | yes    | 1   |
| `caldates2mqtt/{calendar}/error`         | outbound | Per-device error JSON            | no     | 1   |
| `caldates2mqtt/status`                   | outbound | Heartbeat JSON + LWT `"offline"` | yes    | 1   |
| `caldates2mqtt/error`                    | outbound | Error JSON                       | no     | 1   |

`{calendar}` is the `key` from the calendar configuration (e.g. `garbage`, `birthday`).

---

## Payload Schemas

### Calendar State

**Topic:** `caldates2mqtt/{calendar}/state`

Published after each successful CalDAV poll. Contains a list of upcoming all-day events
sorted by date.

```json
{
  "events": [
    {"title": "Gelber Sack", "date": "2026-04-01"},
    {"title": "Restmuell", "date": "2026-04-08"},
    {"title": "Biomuell", "date": "2026-04-10"}
  ]
}
```

| Field    | Type  | Description                                |
| -------- | ----- | ------------------------------------------ |
| `events` | array | List of upcoming all-day events            |
| `events[].title` | string | Event summary from the calendar   |
| `events[].date`  | string | ISO 8601 date (`YYYY-MM-DD`)      |

The number of events is limited by the per-calendar `entries` setting (default: 5), and
only events within the `days` lookahead window are included (default: 14 days).

!!! info "Polling frequency"
    The default polling interval is 7200 seconds (2 hours). The first reading arrives
    shortly after startup; subsequent readings follow the configured interval. See
    [Configuration](configuration.md) to adjust per-calendar.

### Re-Read Command

**Topic:** `caldates2mqtt/{calendar}/set`

Trigger an immediate re-read of a specific calendar. Accepts an empty payload or a JSON
object with optional parameter overrides.

```bash
# Re-read with defaults
mosquitto_pub -h localhost -t "caldates2mqtt/garbage/set" -m ""

# Re-read with overrides
mosquitto_pub -h localhost -t "caldates2mqtt/garbage/set" -m '{"entries":10,"days":30}'
```

| Field     | Type    | Required | Description                                   |
| --------- | ------- | -------- | --------------------------------------------- |
| `entries` | integer | no       | Override number of events to return            |
| `days`    | integer | no       | Override lookahead window in days              |

Overrides apply only to this single re-read; the next scheduled poll uses the configured
defaults.

### Availability

**Topic:** `caldates2mqtt/{calendar}/availability`

Managed automatically by the cosalette framework. Published when the device comes online
or goes offline.

```text
"online"     # device is running and reachable
"offline"    # device has stopped or is unreachable
```

### Status (Heartbeat)

**Topic:** `caldates2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last Will
and Testament (LWT) --- the broker publishes `"offline"` if caldates2mqtt disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime": 3600.0,
  "version": "0.1.0",
  "devices": {
    "garbage": { "status": "online" },
    "birthday": { "status": "online" }
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

**Topic:** `caldates2mqtt/error`

Published (not retained) when an error occurs. The cosalette framework deduplicates
consecutive identical errors. CalDAV-specific errors (authentication failures, connection
timeouts) are the most common.

```json
{
  "type": "CalDavConnectionError",
  "message": "Failed to connect to cloud.example.com",
  "device": "garbage",
  "timestamp": 1700000000.0
}
```

| Field       | Type   | Description                            |
| ----------- | ------ | -------------------------------------- |
| `type`      | string | Python exception class name            |
| `message`   | string | Human-readable error description       |
| `device`    | string | Calendar device that raised the error  |
| `timestamp` | float  | Unix timestamp when the error occurred |

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `caldates2mqtt/{calendar}/error`. The payload format is the same.

---

## Topic Naming Convention

caldates2mqtt follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment   | Value                                                           |
| --------- | --------------------------------------------------------------- |
| `prefix`  | App name --- `caldates2mqtt` by default (configurable)          |
| `device`  | Calendar `key` from config (e.g. `garbage`, `birthday`)         |
| `channel` | `state`, `set`, `availability`, or `error`                      |

Global topics (`status`, `error`) omit the device segment:

```text
caldates2mqtt/status
caldates2mqtt/error
```

The topic prefix is configurable via `CALDATES2MQTT_MQTT__TOPIC_PREFIX`. See
[Configuration](configuration.md) for details.
