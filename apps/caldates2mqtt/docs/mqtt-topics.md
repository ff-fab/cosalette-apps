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

The number of events is limited by the per-calendar `entries` setting (default: 5,
maximum: 50), and only events within the `days` lookahead window are included (default:
14 days, maximum: 365). Titles longer than 100 characters are cut to 100 characters.

!!! info "Home Assistant"
    On connect, the app publishes retained Home Assistant discovery configs to
    `homeassistant/sensor/caldates2mqtt/{calendar}_events/config`, creating one sensor
    per calendar, for example `sensor.garbage_events`. The sensor state is the number
    of events. The `events`
    attribute carries the list above, so a template can read
    `state_attr('sensor.garbage_events', 'events')`. The Home Assistant recorder keeps
    these titles in its history.

!!! info "openHAB"
    `task caldates2mqtt:schema:openhab` generates one `Number` item per calendar. The
    item holds the event count and reads it with
    `JSONPATH:$.events.length()`. openHAB gets the count only, not the event list.

    Each generated Thing also declares the `availabilityTopic` of its calendar. If the
    calendar publishes `offline`, openHAB shows the Thing as OFFLINE. Regenerate your
    Things after you upgrade to get this wiring.

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
"online"     # no availability source currently marks the entity offline
"offline"    # stale telemetry, a stopped task/app, or a reachability failure
```

### Status (Heartbeat)

**Topic:** `caldates2mqtt/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last Will
and Testament (LWT) --- the broker publishes `"offline"` if caldates2mqtt disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime_s": 3600,
  "version": "0.1.0",
  "devices": {
    "garbage": {
      "status": "ok",
      "last_success_at": "2026-10-01T18:34:58+00:00",
      "consecutive_failures": 0,
      "last_error": null,
      "failing_since": null
    },
    "birthday": {
      "status": "ok",
      "last_success_at": "2026-10-01T18:34:58+00:00",
      "consecutive_failures": 0,
      "last_error": null,
      "failing_since": null
    }
  }
}
```

| Field     | Type   | Description                                    |
| --------- | ------ | ---------------------------------------------- |
| `status`  | string | `"online"` or `"offline"`                      |
| `uptime_s` | integer  | Seconds since application start                |
| `version` | string | Application version                            |
| `devices` | object | Per-device status map                          |

`uptime_s` is an integer. Telemetry entries include `last_success_at` (ISO 8601
string, or `null` before the first success), `consecutive_failures` (integer),
`last_error` (error type, or `null`) and `failing_since` (ISO 8601 string, or
`null`). The last two values are populated during failures and reset to `null`
on success. Device statuses are `"ok"`, `"error"`, `"unavailable"`,
`"circuit_open"` or `"stale"`; stale freshness takes precedence. The freshness
watchdog marks a calendar offline after the derived window of two schedule gaps
plus the retry/backoff budget: 14616 s (about 4 h 4 min) for the default
two-hour schedule. A successful handler cycle clears that freshness mark, even
when an unchanged value is not republished. A stale calendar does not stop
caldates2mqtt; see
[Configuration > Health and recovery](configuration.md#health-and-recovery).

### Error

**Topic:** `caldates2mqtt/error`

Published (not retained) when an error occurs. The cosalette framework deduplicates
consecutive identical telemetry errors: a persisting error is republished as a reminder (2nd, 4th, 8th, ... failure in the first hour, then hourly) carrying `details.count` and `details.first_seen`; count `1` marks a new incident. CalDAV-specific errors (authentication failures, connection
timeouts) are the most common.

```json
{
  "error_type": "caldav_connection",
  "message": "Failed to connect to cloud.example.com",
  "device": "garbage",
  "timestamp": "2026-10-01T18:34:58+00:00",
  "id": "c0ffee000001",
  "details": {"count": 1, "first_seen": "2026-10-01T18:34:58+00:00"}
}
```

| Field        | Type   | Description                                      |
| ------------ | ------ | ------------------------------------------------ |
| `error_type` | string | Machine-readable error identifier                |
| `message`    | string | Sanitized domain message; otherwise class name   |
| `device`     | string | Calendar device that raised the error            |
| `timestamp`  | string | ISO 8601 time when the error occurred             |
| `id`         | string | Correlation id matching the local log line        |
| `details`    | object | Telemetry streak `count` and `first_seen`         |

Domain error identifiers are `caldav_error`, `caldav_auth`,
`caldav_connection`, `caldav_not_found`, `caldav_timeout` and `caldav_read`.
Unmapped exceptions use `error_type: "error"` and disclose only the exception
class name by default.

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific errors to
    `caldates2mqtt/{calendar}/error`. The payload format is the same.

---

## Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
the tables above expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless caldates2mqtt refreshes it. caldates2mqtt re-publishes each retained topic with an unchanged
payload every third of that interval (8 hours by default). Non-retained topics, such as
`caldates2mqtt/error`, carry no expiry. See
[MQTT 5 retained-message expiry](configuration.md#mqtt-5-retained-message-expiry) for the
operator contract and the MQTT 3.1.1 fallback.

---

## Framework Topics

Alongside the caldates2mqtt-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on — no setting disables them — retained,
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
