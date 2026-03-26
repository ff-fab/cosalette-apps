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

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `AIRTHINGS2MQTT_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

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
