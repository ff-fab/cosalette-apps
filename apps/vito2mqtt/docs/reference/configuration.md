---
title: Configuration Reference
---

# Configuration Reference

vito2mqtt is configured via environment variables or a `.env` file. All variables
use the `VITO2MQTT_` prefix. Settings are validated at startup using
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
through the [cosalette](https://github.com/ff-fab/cosalette) framework.

---

## Base Settings (from cosalette)

These settings are inherited from the cosalette `Settings` base class:

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `VITO2MQTT_MQTT__HOST` | MQTT broker hostname or IP | `localhost` |
| `VITO2MQTT_MQTT__PORT` | MQTT broker port | `1883` |
| `VITO2MQTT_MQTT__USERNAME` | MQTT username (optional) | — |
| `VITO2MQTT_MQTT__PASSWORD` | MQTT password (optional) | — |
| `VITO2MQTT_MQTT__PROTOCOL_VERSION` | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below | `3.1.1` in code, `5` in compose |
| `VITO2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` | `86400` |
| `VITO2MQTT_LOGGING__LEVEL` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | `INFO` |

!!! note "Nested delimiter"
    MQTT settings use `__` (double underscore) as the nested delimiter. The variable
    `VITO2MQTT_MQTT__HOST` maps to the `mqtt.host` field in the settings model.
    This is the standard
    [pydantic-settings nested model convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values).

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects vito2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): the group state topics, availability, the legionella
status, Home Assistant discovery, `status`, `_meta/*` and the last will. While
vito2mqtt runs, it re-publishes each retained topic every third of that interval
(default 8 hours), so the topics stay alive. A topic that nothing refreshes any more,
such as a renamed entity or a stopped process, disappears from the broker by itself.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, vito2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `VITO2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If vito2mqtt is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics. vito2mqtt publishes
  every group again at startup, so the state topics return with the restart.
- **Consumers see one repeat per refresh.** Group state is published only when a value
  changes, so a stable group stays silent for hours. With MQTT 5 the broker also gets the
  last payload of each group again every 8 hours. The repeat has the same payload, and
  the broker forwards it to live subscribers without the retain flag, so it looks like a
  normal message. Home Assistant sensors do not change state on a repeat. An automation
  that triggers on receipt of a `{group}/state` message runs once more per refresh;
  trigger on a value change instead.
- **A repeat never drives the boiler.** vito2mqtt writes to the boiler only on the
  `{group}/set` topics, which are never retained and never refreshed.

---

## Application Settings

These settings are specific to vito2mqtt and defined in `Vito2MqttSettings`:

### Connection

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `serial_port` | `VITO2MQTT_SERIAL_PORT` | `str` | **Required** | Serial device path (e.g., `/dev/ttyUSB0`) |
| `serial_baud_rate` | `VITO2MQTT_SERIAL_BAUD_RATE` | `int` | `4800` | Baud rate for Optolink connection |

### Signal Language

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `signal_language` | `VITO2MQTT_SIGNAL_LANGUAGE` | `"de"` \| `"en"` | `"en"` | Language for signal names |

### Polling Intervals

Per-domain polling intervals in seconds. Each controls how often a signal group is
read from the boiler.

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `polling_outdoor` | `VITO2MQTT_POLLING_OUTDOOR` | `float` | `300.0` | Outdoor sensors polling interval |
| `polling_hot_water` | `VITO2MQTT_POLLING_HOT_WATER` | `float` | `300.0` | Hot water polling interval |
| `polling_burner` | `VITO2MQTT_POLLING_BURNER` | `float` | `300.0` | Burner telemetry polling interval |
| `polling_heating_radiator` | `VITO2MQTT_POLLING_HEATING_RADIATOR` | `float` | `300.0` | M1 radiator circuit polling interval |
| `polling_heating_floor` | `VITO2MQTT_POLLING_HEATING_FLOOR` | `float` | `300.0` | M2 floor heating circuit polling interval |
| `polling_system` | `VITO2MQTT_POLLING_SYSTEM` | `float` | `3600.0` | System info polling interval |
| `polling_diagnosis` | `VITO2MQTT_POLLING_DIAGNOSIS` | `float` | `300.0` | Diagnosis/error polling interval |
| `command_wake_min_interval` | `VITO2MQTT_COMMAND_WAKE_MIN_INTERVAL` | `float` | `15.0` | Floor on the spacing between two command-triggered telemetry runs (seconds) |

!!! tip "Polling tuning"
    All intervals must be greater than zero. Outdoor and diagnosis groups default to
    5 minutes (300s). The system group defaults to 1 hour (3600s) since its signals
    change infrequently. Adjust based on your monitoring needs vs. serial bus load.

!!! info "Polling intervals no longer bound command feedback"
    A successful write on a `/set` topic wakes that group's telemetry handler
    directly, so the boiler is re-read within seconds rather than at the next
    tick. Treat these intervals as the heartbeat and staleness bound, not
    as the latency you will observe after changing a setting.

    Repeated writes are throttled to one extra read per group per
    `command_wake_min_interval` seconds (default 15) so a burst — a full weekly
    timer schedule is seven separate payloads — cannot saturate the 4800-baud
    bus. A write arriving inside that window is held, not dropped. **Raise it**
    (`VITO2MQTT_COMMAND_WAKE_MIN_INTERVAL`) for a slower bus or a busier command
    load; **lower it** for snappier command-driven refreshes at the cost of more
    serial contention. Must be `> 0`.

### Legionella Treatment

Settings for the automated legionella prevention cycle. The treatment temporarily
raises hot water temperature to kill bacteria.

| Setting | Environment Variable | Type | Default | Description |
|---------|---------------------|------|---------|-------------|
| `legionella_temperature` | `VITO2MQTT_LEGIONELLA_TEMPERATURE` | `int` | `68` | Target hot water temp during treatment (°C) |
| `legionella_duration_minutes` | `VITO2MQTT_LEGIONELLA_DURATION_MINUTES` | `int` | `40` | Duration of treatment cycle (minutes) |
| `legionella_safety_margin_minutes` | `VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES` | `int` | `30` | Minimum remaining heating-window time for treatment to start (minutes) |

!!! warning "Legionella safety"
    The safety margin ensures the treatment only starts if there is enough time
    remaining in the current heating window to complete the full cycle. Setting this
    too low risks an incomplete treatment.

### State Persistence

The device store records runtime state such as legionella treatment timestamps.
By default, the store file is located following the
[XDG Base Directory](https://specifications.freedesktop.org/basedir-spec/latest/)
convention.

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `VITO2MQTT_STORE_PATH` | `str` | `~/.local/state/vito2mqtt/store.json` | Path to JSON store file |

Resolution order:

1. `VITO2MQTT_STORE_PATH` — explicit override (highest priority)
2. `$XDG_STATE_HOME/vito2mqtt/store.json` — XDG state directory
3. `~/.local/state/vito2mqtt/store.json` — XDG default fallback

!!! tip "Docker deployments"
    In Docker, set `VITO2MQTT_STORE_PATH=/data/store.json` and mount a named volume
    at `/data` to persist state across container restarts. The provided
    `compose.yml` configures this automatically.

Parent directories are created automatically on first write.

---

## Complete `.env` Example

```bash title=".env"
# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0
VITO2MQTT_SERIAL_BAUD_RATE=4800

# ---------------------------------------------------------------------------
# MQTT Broker
# ---------------------------------------------------------------------------
VITO2MQTT_MQTT__HOST=192.168.1.100
VITO2MQTT_MQTT__PORT=1883
VITO2MQTT_MQTT__USERNAME=vito2mqtt
VITO2MQTT_MQTT__PASSWORD=secret

# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------
VITO2MQTT_SIGNAL_LANGUAGE=en
VITO2MQTT_LOGGING__LEVEL=INFO

# ---------------------------------------------------------------------------
# State Persistence (optional — defaults to XDG_STATE_HOME)
# ---------------------------------------------------------------------------
# VITO2MQTT_STORE_PATH=/custom/path/store.json

# ---------------------------------------------------------------------------
# Polling Intervals (seconds)
# ---------------------------------------------------------------------------
VITO2MQTT_POLLING_OUTDOOR=300
VITO2MQTT_POLLING_HOT_WATER=300
VITO2MQTT_POLLING_BURNER=300
VITO2MQTT_POLLING_HEATING_RADIATOR=300
VITO2MQTT_POLLING_HEATING_FLOOR=300
VITO2MQTT_POLLING_SYSTEM=3600
VITO2MQTT_POLLING_DIAGNOSIS=300

# Floor on command-triggered telemetry runs, seconds, must be > 0 (default: 15)
# VITO2MQTT_COMMAND_WAKE_MIN_INTERVAL=15

# ---------------------------------------------------------------------------
# Legionella Treatment
# ---------------------------------------------------------------------------
VITO2MQTT_LEGIONELLA_TEMPERATURE=68
VITO2MQTT_LEGIONELLA_DURATION_MINUTES=40
VITO2MQTT_LEGIONELLA_SAFETY_MARGIN_MINUTES=30
```
