# MQTT Topics

suncast publishes shadow visualizations, health information, and errors to a set of
MQTT topics under the `suncast/` prefix. suncast is a pure telemetry service — there
are **no inbound command topics**.

---

## Topic Overview

| Topic                            | Dir      | Payload              | Retain | QoS |
| -------------------------------- | -------- | -------------------- | ------ | --- |
| `suncast/status`                 | outbound | Heartbeat JSON       | yes    | 1   |
| `suncast/shadow/svg`             | outbound | Raw SVG string       | yes    | 1   |
| `suncast/shadow/png`             | outbound | Base64 PNG           | yes    | 1   |
| `suncast/shadow/availability`    | outbound | `"online"`/`"offline"` | yes  | 1   |
| `suncast/shadow/error`           | outbound | Error JSON           | no     | 1   |
| `suncast/error`                  | outbound | Error JSON           | no     | 1   |

---

## Payload Schemas

### Status (Heartbeat)

**Topic:** `suncast/status`

Periodic heartbeat published by the cosalette health reporter. Also used as the Last
Will and Testament (LWT) — the broker publishes `"offline"` if suncast disconnects
unexpectedly.

```json
{
  "status": "online",
  "uptime": 3600.5,
  "version": "0.1.0",
  "devices": {
    "shadow": { "status": "online", "last_seen": 1700000000.0 }
  }
}
```

### Shadow SVG

**Topic:** `suncast/shadow/svg`

Raw SVG string. Published every poll cycle. Subscribe and render directly in
your dashboard (e.g. Home Assistant picture-elements card, Grafana HTML panel).

### Shadow PNG

**Topic:** `suncast/shadow/png`

Base64-encoded PNG image. Only published when `SUNCAST_PNG_ENABLED=true`.
Requires the `png` extra:

```bash
pip install suncast[png]
```

### Shadow State

The shadow device publishes visualization data via the `svg` and `png` channels
rather than the standard `state` topic. The telemetry handler returns `None`,
so no `suncast/shadow/state` message is published by the framework.

### Availability

**Topic:** `suncast/shadow/availability`

Each device publishes its availability status. The cosalette framework manages
these automatically.

```text
"online"     # device is running
"offline"    # device has stopped (or app shutting down)
```

### Error

**Topics:** `suncast/error`, `suncast/shadow/error`

Published (not retained) when a device encounters an error. The cosalette framework
deduplicates consecutive identical errors.

```json
{
  "type": "OSError",
  "message": "Geometry file not found",
  "device": "shadow",
  "timestamp": 1700000000.0
}
```

!!! info "Per-device error topics"
    In addition to the global error topic, cosalette publishes device-specific
    errors to `suncast/shadow/error`. Both topics use the same payload format.

---

## Framework Topics

Alongside the suncast-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on -- no setting disables them -- retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `suncast/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `suncast/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`suncast/_meta/registry`)

The canonical AsyncAPI document describing every channel suncast publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`suncast/_meta/state_model_drift`)

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

suncast follows the cosalette topic convention:

```text
{prefix}/{device}/{channel}
```

| Segment   | Value                                            |
| --------- | ------------------------------------------------ |
| `prefix`  | App name — `suncast` by default                  |
| `device`  | Device name: `shadow`                            |
| `channel` | `svg`, `png`, `availability`, or `error`         |

Global topics (`status`, `error`) omit the device segment:

```text
suncast/status
suncast/error
```
