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
