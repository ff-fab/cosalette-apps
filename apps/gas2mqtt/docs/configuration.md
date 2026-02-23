# Configuration

gas2mqtt uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for configuration, giving you three ways to set any value:

1. **CLI flags** — highest priority
2. **Environment variables** — `GAS2MQTT_` prefix
3. **`.env` file** — loaded from the working directory
4. **Defaults** — built-in sensible values

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting       | Env Variable                | Default     | Description                |
| ------------- | --------------------------- | ----------- | -------------------------- |
| Host          | `GAS2MQTT_MQTT__HOST`       | `localhost` | MQTT broker hostname       |
| Port          | `GAS2MQTT_MQTT__PORT`       | `1883`      | MQTT broker port           |
| Username      | `GAS2MQTT_MQTT__USERNAME`   | —           | Broker username            |
| Password      | `GAS2MQTT_MQTT__PASSWORD`   | —           | Broker password            |
| Client ID     | `GAS2MQTT_MQTT__CLIENT_ID`  | *(auto)*    | MQTT client identifier (auto-generated if empty) |
| Topic prefix  | `GAS2MQTT_MQTT__TOPIC_PREFIX` | *(app name)* | Root prefix for all MQTT topics |
| Reconnect interval | `GAS2MQTT_MQTT__RECONNECT_INTERVAL` | `5.0` | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `GAS2MQTT_MQTT__RECONNECT_MAX_INTERVAL` | `300.0` | Upper bound for reconnect backoff (seconds) |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `GAS2MQTT_MQTT__HOST` → `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### Logging

| Setting       | Env Variable                    | Default  | Description                   |
| ------------- | ------------------------------- | -------- | ----------------------------- |
| Level         | `GAS2MQTT_LOGGING__LEVEL`       | `INFO`   | Root log level                |
| Format        | `GAS2MQTT_LOGGING__FORMAT`      | `json`   | `json` or `text` output format |
| File          | `GAS2MQTT_LOGGING__FILE`        | —        | Optional log file path        |
| Max file size | `GAS2MQTT_LOGGING__MAX_FILE_SIZE_MB` | `10` | Max log file size in MB before rotation |
| Backup count  | `GAS2MQTT_LOGGING__BACKUP_COUNT` | `3`     | Number of rotated log files to keep |

!!! tip "Choosing a log format"
    Use `json` (the default) for Docker and container environments — structured logs
    are easier to parse with log aggregators. Use `text` for local development where
    human-readable output is more convenient.

### I2C / Sensor

| Setting       | Env Variable              | Default       | Description                          |
| ------------- | ------------------------- | ------------- | ------------------------------------ |
| I2C bus       | `GAS2MQTT_I2C_BUS`       | `1`           | I2C bus number                       |
| I2C address   | `GAS2MQTT_I2C_ADDRESS`   | `13` (0x0D)   | QMC5883L I2C address (decimal)       |

### Schmitt Trigger

| Setting       | Env Variable                   | Default   | Description                          |
| ------------- | ------------------------------ | --------- | ------------------------------------ |
| Trigger level | `GAS2MQTT_TRIGGER_LEVEL`       | `-5000`   | Bz centre threshold                  |
| Hysteresis    | `GAS2MQTT_TRIGGER_HYSTERESIS`  | `700`     | Dead-band half-width around level    |

!!! tip "Calibrating the trigger"
    Enable the debug magnetometer device (`GAS2MQTT_ENABLE_DEBUG_DEVICE=true`) to see
    raw Bz values. Observe the range as the gas meter rotates, then set the trigger
    level to the midpoint and hysteresis to half the swing.

!!! note "Switching thresholds"
    The Schmitt trigger uses two thresholds derived from your settings:

    - **Upper threshold** = `trigger_level + trigger_hysteresis`
    - **Lower threshold** = `trigger_level − trigger_hysteresis`

    With defaults (`-5000` / `700`), the trigger closes at **−4300** and opens at
    **−5700**.

### Polling

| Setting              | Env Variable                      | Default  | Description                           |
| -------------------- | --------------------------------- | -------- | ------------------------------------- |
| Poll interval        | `GAS2MQTT_POLL_INTERVAL`          | `1.0`    | Gas counter polling interval (seconds)|
| Temperature interval | `GAS2MQTT_TEMPERATURE_INTERVAL`   | `300.0`  | Temperature report interval (seconds) |

!!! warning "Registration-time settings"
    `poll_interval`, `temperature_interval`, and `enable_debug_device` are read **once
    at application startup** from their field defaults. Environment variables and `.env`
    overrides do **not** affect these values because cosalette's `@app.telemetry`
    decorator requires compile-time constants for the `interval` parameter, and
    conditional device registration is resolved before the settings model is
    instantiated.

    To change the polling interval or enable the debug device, modify the defaults in
    the source code and rebuild. Runtime settings (calibration coefficients, I2C
    addresses, MQTT configuration) are injected normally via cosalette's DI system and
    **do** respect environment variables.

### Temperature Calibration

| Setting     | Env Variable              | Default | Description                    |
| ----------- | ------------------------- | ------- | ------------------------------ |
| Scale       | `GAS2MQTT_TEMP_SCALE`     | `0.008` | Calibration scale factor       |
| Offset      | `GAS2MQTT_TEMP_OFFSET`    | `20.3`  | Calibration offset (°C)        |
| EWMA alpha  | `GAS2MQTT_EWMA_ALPHA`     | `0.2`   | Smoothing factor (0–1)         |

The QMC5883L has a built-in temperature sensor. gas2mqtt applies an empirical linear
calibration: `temp_celsius = temp_scale × raw + temp_offset`. The EWMA filter smooths
readings to reduce noise — lower alpha values produce smoother output.

### Optional Features

| Setting              | Env Variable                           | Default  | Description                     |
| -------------------- | -------------------------------------- | -------- | ------------------------------- |
| Consumption tracking | `GAS2MQTT_ENABLE_CONSUMPTION_TRACKING` | `false`  | Enable cumulative m³ tracking   |
| Liters per tick      | `GAS2MQTT_LITERS_PER_TICK`             | `10.0`   | Gas liters per counter tick     |
| Debug device         | `GAS2MQTT_ENABLE_DEBUG_DEVICE`         | `false`  | Enable raw magnetometer output  |

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# gas2mqtt Configuration
# All settings can be set via environment variables with GAS2MQTT_ prefix.
# Nested settings use __ delimiter (e.g., GAS2MQTT_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
GAS2MQTT_MQTT__HOST=localhost
GAS2MQTT_MQTT__PORT=1883
# GAS2MQTT_MQTT__USERNAME=
# GAS2MQTT_MQTT__PASSWORD=
# GAS2MQTT_MQTT__CLIENT_ID=gas2mqtt
# GAS2MQTT_MQTT__TOPIC_PREFIX=gas2mqtt

# --- Logging ---
# GAS2MQTT_LOGGING__LEVEL=INFO

# --- I2C Configuration ---
# GAS2MQTT_I2C_BUS=1
# GAS2MQTT_I2C_ADDRESS=13  # 0x0D in decimal

# --- Schmitt Trigger ---
# GAS2MQTT_TRIGGER_LEVEL=-5000
# GAS2MQTT_TRIGGER_HYSTERESIS=700

# --- Polling ---
# GAS2MQTT_POLL_INTERVAL=1.0
# GAS2MQTT_TEMPERATURE_INTERVAL=300.0

# --- Temperature Calibration ---
# GAS2MQTT_TEMP_SCALE=0.008
# GAS2MQTT_TEMP_OFFSET=20.3
# GAS2MQTT_EWMA_ALPHA=0.2

# --- Consumption Tracking ---
# GAS2MQTT_ENABLE_CONSUMPTION_TRACKING=false
# GAS2MQTT_LITERS_PER_TICK=10.0

# --- Debug ---
# GAS2MQTT_ENABLE_DEBUG_DEVICE=false
```

Uncomment and modify any line to override the default.

---

## Pydantic Settings

Under the hood, gas2mqtt extends the cosalette framework's `Settings` base class with
its own `Gas2MqttSettings`. This uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) which
provides:

- **Type validation** — invalid values fail fast at startup with clear error messages
- **Multiple sources** — environment variables, `.env` files, CLI flags, YAML, TOML
- **Nested models** — MQTT settings are a sub-model, accessed via `__` delimiter

See the [pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for advanced usage.
