# MQTT Topics

wallpanel-control exposes a typed JSON MQTT API. All payloads are JSON objects;
unknown fields are rejected with an error publication.

!!! warning "`discoverable=False` is not access control"

    A channel marked `discoverable=False` is omitted from Home Assistant discovery
    output. It is **still subscribed and still acts on what it receives.** The flag
    changes what Home Assistant is told about, not who may publish. Anyone who can
    reach the broker can still drive these topics, and the bundled broker in
    `compose.yml` is plaintext with `allow_anonymous true`. Restrict
    access with broker ACLs and `<PREFIX>_MQTT__TLS=true`, not with this flag.

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
    wallpanel-control publishes no periodic readings. State is published in response to
    commands and, by the panel probe, only when the panel's reachability changes (see
    [Panel probe](configuration.md#panel-probe)). The cosalette framework independently
    publishes its own health/heartbeat to `{prefix}/status`. No device ever reports
    `stale` there; see [Health and recovery](configuration.md#health-and-recovery).

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
command is rejected and an error with `error_type: "invalid_payload"` is published to
`wallpanel-control/error`; see [Errors](#errors).

### State: `wallpanel-control/display/state`

Published (QoS 1, retained) after each accepted display command, and by the panel
probe when the panel stops or starts answering over SSH.

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

Published (QoS 1, retained) as an acknowledgement after each system action command,
and again by the panel probe when it resolves `observed`.

Successful acknowledgement, while the probe waits for the panel:

```json
{ "accepted": true, "action": "wake", "observed": "pending" }
```

If the action was rejected (e.g. SSH error):

```json
{ "accepted": false, "action": "suspend", "observed": null }
```

| `observed`    | Meaning                                                                 |
| ------------- | ----------------------------------------------------------------------- |
| `"pending"`   | accepted; the probe waits for the panel                                 |
| `"confirmed"` | the panel answered (wake) or stopped answering (suspend, hibernate)     |
| `"timeout"`   | no change within `ACTION_CONFIRM_TIMEOUT` (90 s by default)             |
| `null`        | not accepted, the probe is off, or the app restarted while it was pending |

!!! note "wake vs. SSH actions"
    `wake` sends a UDP magic packet via Wake-on-LAN -- it does not use SSH. `suspend`
    and `hibernate` run `systemctl suspend` / `systemctl hibernate` over SSH and
    require the SSH connection to be available.

### What `accepted` means

`accepted: true` confirms the request, not its outcome:

| Action                  | `accepted: true` means                                  |
| ----------------------- | ------------------------------------------------------- |
| `suspend`, `hibernate`  | logind took the sleep request over SSH                  |
| `wake`                  | the app sent the magic packet                           |

The panel probe reports the outcome in `observed`, and `display/state` turns
`"available": false` once the panel no longer answers over SSH. With the probe off,
nothing confirms that the panel went to sleep or woke up.

On a GNOME session, gnome-shell holds a delay inhibitor, so logind waits up to
`InhibitDelayMaxSec` (30 seconds by default) before the panel sleeps. The panel stays
reachable in that window. Lower the delay in `/etc/systemd/logind.conf` on the panel if
the wait matters to your automations.

A repeated `suspend` or `hibernate` of the same type during that window also answers
`accepted: true` and publishes no error: logind refuses the duplicate because that
sleep is already pending. A different pending power operation cannot be identified
from logind's refusal message, so it remains an error.

A `wake` answers `accepted: true` even when the packet cannot reach the panel, for
example from a Docker bridge network. See
[Wake-on-LAN](configuration.md#wake-on-lan).

---

## Errors

### `wallpanel-control/error`

Published (QoS 1, **not** retained) when the app encounters a command handler,
validation, or adapter-level failure. For non-root commands, cosalette also publishes the
same payload to the per-command error topic, such as `wallpanel-control/display/error`
or `wallpanel-control/system/action/error`.

A rejected payload publishes `error_type: "invalid_payload"`. Its `message` names the
command parameter and the pydantic type code of each failure. Field names render as
`[field]` and a cross-field rule as `__root__`, and the rejected value is never included:

```json
{
    "error_type": "invalid_payload",
    "message": "Payload validation failed (parameter 'cmd'): [field]: type=less_than_equal",
    "device": "display",
    "timestamp": "2026-02-14T12:34:56+00:00",
    "details": {}
}
```

A handler that exceeds its watchdog publishes `error_type: "timeout"` with the
message `TimeoutError` (unless `WALLPANEL_CONTROL_MQTT__ERROR_PUBLISH_VERBOSE` is
`true`). Every other failure publishes `error_type: "error"` and only the exception class name:

```json
{
    "error_type": "error",
    "message": "RuntimeError",
    "device": "system/action",
    "timestamp": "2026-02-14T12:34:56+00:00",
    "details": {}
}
```

The payload also carries a correlation `id`. The full exception text, which can include
the SSH host and user, goes to the app log under that `id`. Set
`WALLPANEL_CONTROL_MQTT__ERROR_PUBLISH_VERBOSE=true` to publish it on the broker too.

This topic carries transient error notifications. Do not rely on retained state from
this topic -- it is never retained.

---

## Retention and Expiry

With MQTT 5 enabled (the default in the shipped `compose.yml`), every retained topic in
the tables above expires after `MESSAGE_EXPIRY_INTERVAL` seconds (24 hours by default)
unless wallpanel-control refreshes it. wallpanel-control re-publishes each retained
topic with an unchanged payload every third of that interval (8 hours by default). The
`display/state` and `system/action/state` answers exist only after a command or a probe
publication, so wallpanel-control saves them in its store and publishes them again at startup.
Non-retained topics, such as the `error` topic and the `/set` topics, carry no expiry.
See
[MQTT 5 retained-message expiry](configuration.md#mqtt-5-retained-message-expiry) for the
operator contract and the MQTT 3.1.1 fallback.

---

## Unavailable Behavior

When the wall panel is unreachable, accepted display commands and the panel probe
publish a state with `"available": false` and null values for `state` and `brightness_percent`. No
separate availability topic is used -- availability is embedded in each state payload.

If `suspend` or `hibernate` cannot be sent because the wall panel is unreachable,
the acknowledgement uses `accepted: false`. A sleep request that logind refuses because
an earlier one is still pending answers `accepted: true`; see
[What `accepted` means](#what-accepted-means).

---

## Framework Topics

Alongside the wallpanel-control-specific topics above, cosalette itself publishes two
framework-owned topics. Both are always on — no setting disables them — retained,
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
