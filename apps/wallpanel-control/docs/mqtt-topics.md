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
| `wallpanel-control/error`               | Publish   | 1   | No       | Global app-level error event       |
| `wallpanel-control/<command>/error`     | Publish   | 1   | No       | Per-command error event            |

!!! info "Topic prefix"
    `wallpanel-control` is the default topic prefix. It can be changed via
    `WALLPANEL_CONTROL_MQTT__TOPIC_PREFIX`.

!!! note "No periodic telemetry"
    wallpanel-control is command-driven. State is published only after a command is
    accepted -- there is no background polling or periodic status publication.

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
