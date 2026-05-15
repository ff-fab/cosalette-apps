# MQTT Topics

wallpanel-control exposes a small typed JSON MQTT API. All payloads are JSON
objects; unknown fields are rejected.

## Display

Use `wallpanel-control/display/set` to change the display state and brightness.
The app publishes the resulting state to `wallpanel-control/display/state` after
each accepted command.

### Commands

Turn the display on:

```json
{ "state": "on" }
```

Turn the display off:

```json
{ "state": "off" }
```

Set brightness. This uses a percentage from `1` to `100`; `0` is not accepted as
an off command.

```json
{ "brightness_percent": 60 }
```

Turn on and set brightness in one command:

```json
{ "state": "on", "brightness_percent": 60 }
```

### State

When the wallpanel is reachable:

```json
{ "available": true, "state": "on", "brightness_percent": 60 }
```

When the wallpanel is unreachable:

```json
{ "available": false, "state": null, "brightness_percent": null }
```

## System Actions

Use `wallpanel-control/system/action/set` for machine-level power actions. The
app publishes an acknowledgement to `wallpanel-control/system/action/state`.

Wake the wallpanel via Wake-on-LAN:

```json
{ "action": "wake" }
```

Suspend the wallpanel:

```json
{ "action": "suspend" }
```

Hibernate the wallpanel:

```json
{ "action": "hibernate" }
```

Acknowledgement payload:

```json
{ "accepted": true, "action": "wake" }
```

If `suspend` or `hibernate` cannot be sent because the wallpanel is unreachable,
the acknowledgement uses `accepted: false`.
