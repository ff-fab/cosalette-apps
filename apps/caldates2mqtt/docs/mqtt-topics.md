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

!!! info "Polling schedule"
    By default, calendars are polled every 2 hours (Quartz cron `"0 0 0/2 * * ?"`).
    The first reading arrives shortly after startup; subsequent reads follow the
    configured schedule. See [Configuration](configuration.md) to adjust per-calendar.

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

!!! note "Re-reads are rate limited"

    Consecutive re-reads of the same calendar are spaced at least 60 seconds apart. A
    command that arrives inside that window is *delayed*, not dropped — the re-read
    still happens once the window reopens. This keeps a stuck automation from turning
    into a request flood against the CalDAV server. The configured schedule is
    unaffected.

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

## Framework Topics

Alongside the caldates2mqtt-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on -- no setting disables them -- retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `caldates2mqtt/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `caldates2mqtt/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`caldates2mqtt/_meta/registry`)

The canonical AsyncAPI document describing every channel caldates2mqtt publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`caldates2mqtt/_meta/state_model_drift`)

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
