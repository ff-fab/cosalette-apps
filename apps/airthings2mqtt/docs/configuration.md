# Configuration

airthings2mqtt uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration. Values can come from three sources that override built-in defaults:

1. **CLI flags** --- highest priority
2. **Environment variables** --- `AIRTHINGS2MQTT_` prefix
3. **`.env` file** --- loaded from the working directory

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting            | Env Variable                                | Default      | Description                                            |
| ------------------ | ------------------------------------------- | ------------ | ------------------------------------------------------ |
| Host               | `AIRTHINGS2MQTT_MQTT__HOST`                 | `localhost`  | MQTT broker hostname                                   |
| Port               | `AIRTHINGS2MQTT_MQTT__PORT`                 | `1883`       | MQTT broker port                                       |
| Username           | `AIRTHINGS2MQTT_MQTT__USERNAME`             | ---          | Broker username                                        |
| Password           | `AIRTHINGS2MQTT_MQTT__PASSWORD`             | ---          | Broker password                                        |
| Client ID          | `AIRTHINGS2MQTT_MQTT__CLIENT_ID`            | _(auto)_     | MQTT client identifier (auto-generated if empty)       |
| Topic prefix       | `AIRTHINGS2MQTT_MQTT__TOPIC_PREFIX`         | _(app name)_ | Root prefix for all MQTT topics                        |
| Reconnect interval | `AIRTHINGS2MQTT_MQTT__RECONNECT_INTERVAL`   | `5.0`        | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `AIRTHINGS2MQTT_MQTT__RECONNECT_MAX_INTERVAL`| `300.0`     | Upper bound for reconnect backoff (seconds)            |
| Protocol version   | `AIRTHINGS2MQTT_MQTT__PROTOCOL_VERSION` | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below |
| Message expiry     | `AIRTHINGS2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `AIRTHINGS2MQTT_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects airthings2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): state, availability, Home Assistant discovery, `_meta/*`
and the last will. While airthings2mqtt runs, it re-publishes each retained topic every third
of that interval (default 8 hours), so the topics stay alive. A topic that nothing
refreshes any more, such as a renamed entity or a stopped process, disappears from the
broker by itself.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, airthings2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `AIRTHINGS2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If airthings2mqtt is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics until the next publish.
- **Consumers see one repeat per refresh.** The repeat has the same payload as the last
  publish, and the broker forwards it to live subscribers without the retain flag, so it
  looks like a normal message. Home Assistant sensors do not change state on a repeat.
  `airthings2mqtt/<device>/state` is already published on every poll (25 minutes by
  default), so the refresh adds one identical repeat every 8 hours between two polls.
  A consumer that reacts to message receipt instead of value change sees it.

### Logging

| Setting       | Env Variable                             | Default | Description                             |
| ------------- | ---------------------------------------- | ------- | --------------------------------------- |
| Level         | `AIRTHINGS2MQTT_LOGGING__LEVEL`          | `INFO`  | Root log level                          |
| Format        | `AIRTHINGS2MQTT_LOGGING__FORMAT`         | `json`  | `json` or `text` output format          |
| File          | `AIRTHINGS2MQTT_LOGGING__FILE`           | ---     | Optional log file path                  |
| Max file size | `AIRTHINGS2MQTT_LOGGING__MAX_FILE_SIZE_MB`| `10`   | Max log file size in MB before rotation |
| Backup count  | `AIRTHINGS2MQTT_LOGGING__BACKUP_COUNT`   | `3`     | Number of rotated log files to keep     |

!!! tip "Choosing a log format"
    Use `json` (the default) for Docker and container environments --- structured logs
    are easier to parse with log aggregators. Use `text` for local development where
    human-readable output is more convenient.

### Airthings Sensor

| Setting        | Env Variable                       | Default        | Description                                         |
| -------------- | ---------------------------------- | -------------- | --------------------------------------------------- |
| Device name    | `AIRTHINGS2MQTT_DEVICE_NAME`       | `airthings`    | Friendly name for the sensor in MQTT topics         |
| Device MAC     | `AIRTHINGS2MQTT_DEVICE_MAC`        | _(required)_   | Bluetooth MAC address of the Airthings Wave sensor  |
| Poll interval  | `AIRTHINGS2MQTT_POLL_INTERVAL`     | `1500`         | Polling interval in seconds (minimum 60)            |
| Trigger min interval | `AIRTHINGS2MQTT_TRIGGER_MIN_INTERVAL` | `30.0`  | Minimum seconds between on-demand `/set` re-reads    |

The MQTT entity topics use the configured values as
`{prefix}/{device_name}/{channel}`. For example, setting
`AIRTHINGS2MQTT_DEVICE_NAME=living-room` with the default prefix produces
`airthings2mqtt/living-room/state`, `/set`, `/error`, and `/availability` topics.

!!! note "Finding your device MAC address"
    Use `bluetoothctl` to scan for your Airthings Wave sensor:

    ```bash
    bluetoothctl scan on
    ```

    Look for a device name starting with "Airthings". The MAC address format is
    `XX:XX:XX:XX:XX:XX`.

!!! note "Polling interval"
    Airthings Wave sensors update their internal readings approximately every 5 minutes.
    The default polling interval of 1500 seconds (25 minutes) balances data freshness
    with BLE battery and connection overhead. Values below 60 seconds are rejected at
    startup.

!!! note "Trigger throttle (`TRIGGER_MIN_INTERVAL`)"
    `{prefix}/{device_name}/set` is a public MQTT topic that forces an on-demand
    re-read (`airthings2mqtt/airthings/set` with both defaults). This throttle is the
    minimum spacing (seconds) between two such
    trigger-initiated reads --- a held dashboard button or a runaway automation cannot
    queue more than one BLE round-trip per window. A wake that arrives inside a closed
    window is **held, not dropped**, so the re-read still happens once the window
    reopens. **Raise it** for a flakier sensor or to conserve battery; **lower it** for
    snappier on-demand reads at the cost of more frequent BLE connects. Keep it well
    below `POLL_INTERVAL` so it never throttles the scheduled cadence. Must be `> 0`.

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# airthings2mqtt Configuration
# All settings can be set via environment variables with AIRTHINGS2MQTT_ prefix.
# Nested settings use __ delimiter (e.g., AIRTHINGS2MQTT_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
AIRTHINGS2MQTT_MQTT__HOST=localhost
# Broker terminates plaintext MQTT; see docs/adr/ADR-006.
AIRTHINGS2MQTT_MQTT__TLS=false
# MQTT 5 retained-message expiry; the bundled mosquitto:2 supports it.
# Set to 3.1.1 for a broker without MQTT 5; see docs/adr/ADR-009.
AIRTHINGS2MQTT_MQTT__PROTOCOL_VERSION=5
# AIRTHINGS2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL=86400
AIRTHINGS2MQTT_MQTT__PORT=1883
# AIRTHINGS2MQTT_MQTT__USERNAME=
# AIRTHINGS2MQTT_MQTT__PASSWORD=
# AIRTHINGS2MQTT_MQTT__CLIENT_ID=airthings2mqtt
# AIRTHINGS2MQTT_MQTT__TOPIC_PREFIX=airthings2mqtt

# --- Logging ---
# AIRTHINGS2MQTT_LOGGING__LEVEL=INFO
# AIRTHINGS2MQTT_LOGGING__FORMAT=json

# --- Airthings Sensor ---
# REQUIRED: Bluetooth MAC address of your Airthings Wave sensor
AIRTHINGS2MQTT_DEVICE_MAC=XX:XX:XX:XX:XX:XX

# Friendly name used in MQTT topics (default: airthings)
# AIRTHINGS2MQTT_DEVICE_NAME=airthings

# Polling interval in seconds, minimum 60 (default: 1500 = 25 minutes)
# AIRTHINGS2MQTT_POLL_INTERVAL=1500

# Minimum seconds between on-demand /set re-reads, must be > 0 (default: 30)
# AIRTHINGS2MQTT_TRIGGER_MIN_INTERVAL=30.0
```

Uncomment and modify any line to override the default.

---

## Pydantic Settings

Under the hood, airthings2mqtt extends the cosalette framework's `Settings` base class
with its own `Airthings2MqttSettings`. This uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) which
provides:

- **Type validation** --- invalid values fail fast at startup with clear error messages
- **Multiple sources** --- environment variables, `.env` files, CLI flags, YAML, TOML
- **Nested models** --- MQTT settings are a sub-model, accessed via `__` delimiter

See the
[pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for advanced usage.
