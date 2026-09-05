# MQTT Topics

wallpanel-control exposes a typed JSON MQTT API. All payloads are JSON objects;
unknown fields are rejected with an error publication.

---

## Topic Summary

| Topic                                   | Direction | QoS | Retained | Description                           |
| --------------------------------------- | --------- | --- | -------- | ------------------------------------- |
| `wallpanel-control/display/set`         | Subscribe | 1   | No       | Set display state and/or brightness   |
| `wallpanel-control/display/state`       | Publish   | 1   | Yes      | Current display state                 |
| `wallpanel-control/system/action/set`   | Subscribe | 1   | No       | Trigger a power action                |
| `wallpanel-control/system/action/state` | Publish   | 1   | Yes      | Action acknowledgement                |
| `wallpanel-control/status`              | Publish   | 1   | Yes      | cosalette framework health/heartbeat  |
| `wallpanel-control/error`               | Publish   | 1   | No       | Global app-level error event       |
| `wallpanel-control/<command>/error`     | Publish   | 1   | No       | Per-command error event            |

!!! info "Topic prefix"
    `wallpanel-control` is the default topic prefix. It can be changed via
    `WALLPANEL_CONTROL_MQTT__TOPIC_PREFIX`.

!!! note "No periodic telemetry from hardware"
    wallpanel-control does not poll wallpanel hardware on a timer. State is published
    only in response to commands. The cosalette framework independently publishes its
    own health/heartbeat to `{prefix}/status` regardless of command activity.

---

## Display

### Command: `wallpanel-control/display/set`

| Field               | Type                   | Required | Description                             |
| ------------------- | ---------------------- | -------- | --------------------------------------- |
| `state`             | `"on"` or `"off"`      | No       | Turn the display on or off              |
| `brightness_percent`| integer 1-100          | No       | Set backlight brightness as a percentage |

At least one field is required. Both can be combined in a single message.

Turn the display on:

```json
{ "state": "on" }
```

Turn the display off:

```json
{ "state": "off" }
```

Set brightness to 60% (display state unchanged):

```json
{ "brightness_percent": 60 }
```

Turn on and set brightness in one command:

```json
{ "state": "on", "brightness_percent": 60 }
```

!!! warning "Brightness 0 is not accepted"
    Use `{"state": "off"}` to turn off the display. `{"brightness_percent": 0}` is
    rejected as invalid.

### Validation

If the payload fails validation (unknown fields, out-of-range values, wrong types), the
command is rejected and an error is published to `wallpanel-control/error`.

### State: `wallpanel-control/display/state`

Published (QoS 1, retained) after each accepted display command.

When the wall panel is reachable:

```json
{ "available": true, "state": "on", "brightness_percent": 60 }
```

When the wall panel is unreachable (SSH connection failed):

```json
{ "available": false, "state": null, "brightness_percent": null }
```

---

## System Actions

### Command: `wallpanel-control/system/action/set`

| Field    | Type                                   | Required | Description             |
| -------- | -------------------------------------- | -------- | ----------------------- |
| `action` | `"wake"`, `"suspend"`, or `"hibernate"`| Yes      | Power action to perform |

Wake the wall panel via Wake-on-LAN:

```json
{ "action": "wake" }
```

Suspend the wall panel:

```json
{ "action": "suspend" }
```

Hibernate the wall panel:

```json
{ "action": "hibernate" }
```

### State: `wallpanel-control/system/action/state`

Published (QoS 1, retained) as an acknowledgement after each system action command.

Successful acknowledgement:

```json
{ "accepted": true, "action": "wake" }
```

If the action was rejected (e.g. SSH error):

```json
{ "accepted": false, "action": "suspend" }
```

!!! note "wake vs. SSH actions"
    `wake` sends a UDP magic packet via Wake-on-LAN -- it does not use SSH. `suspend`
    and `hibernate` run `systemctl suspend` / `systemctl hibernate` over SSH and
    require the SSH connection to be available.

---

## Errors

### `wallpanel-control/error`

Published (QoS 1, **not** retained) when the app encounters a command handler,
validation, or adapter-level failure. For non-root commands, cosalette also publishes the
same payload to the per-command error topic, such as `wallpanel-control/display/error`
or `wallpanel-control/system/action/error`.

```json
{
    "error_type": "error",
    "message": "SSH connection refused",
    "device": "display",
    "timestamp": "2026-02-14T12:34:56+00:00",
    "details": {}
}
```

This topic carries transient error notifications. Do not rely on retained state from
this topic -- it is never retained.

---

## Unavailable Behavior

When the wall panel is unreachable, accepted display commands still publish a state
with `"available": false` and null values for `state` and `brightness_percent`. No
separate availability topic is used -- availability is embedded in each state payload.

System action acknowledgements include `"accepted": false` when the SSH call fails.

If `suspend` or `hibernate` cannot be sent because the wallpanel is unreachable,
the acknowledgement uses `accepted: false`.

---

## Framework Topics

Alongside the wallpanel-control-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on -- no setting disables them -- retained,
QoS 1, and republished byte-identically on every broker connect.

| Topic                               | Payload                           | Retain | QoS |
| ------------------------------------ | ---------------------------------- | ------ | --- |
| `wallpanel-control/_meta/registry`            | Canonical AsyncAPI 3.0.0 document   | yes    | 1   |
| `wallpanel-control/_meta/state_model_drift`   | `state_model` drift snapshot JSON   | yes    | 1   |

### Registry (`wallpanel-control/_meta/registry`)

The canonical AsyncAPI document describing every channel wallpanel-control publishes and
subscribes to. Inbound command channels are stripped from the published copy so the
command surface is not exposed to anyone who can subscribe on a shared broker.

### State Model Drift (`wallpanel-control/_meta/state_model_drift`)

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
