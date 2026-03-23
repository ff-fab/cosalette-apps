# Configuration

velux2mqtt uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration. Values can come from three sources that override built-in defaults:

1. **CLI flags** — highest priority
2. **Environment variables** — `VELUX2MQTT_` prefix
3. **`.env` file** — loaded from the working directory

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting            | Env Variable                             | Default      | Description                                            |
| ------------------ | ---------------------------------------- | ------------ | ------------------------------------------------------ |
| Host               | `VELUX2MQTT_MQTT__HOST`                  | `localhost`  | MQTT broker hostname                                   |
| Port               | `VELUX2MQTT_MQTT__PORT`                  | `1883`       | MQTT broker port                                       |
| Username           | `VELUX2MQTT_MQTT__USERNAME`              | ---          | Broker username                                        |
| Password           | `VELUX2MQTT_MQTT__PASSWORD`              | ---          | Broker password                                        |
| Client ID          | `VELUX2MQTT_MQTT__CLIENT_ID`             | _(auto)_     | MQTT client identifier (auto-generated if empty)       |
| Topic prefix       | `VELUX2MQTT_MQTT__TOPIC_PREFIX`          | _(app name)_ | Root prefix for all MQTT topics                        |
| Reconnect interval | `VELUX2MQTT_MQTT__RECONNECT_INTERVAL`    | `5.0`        | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `VELUX2MQTT_MQTT__RECONNECT_MAX_INTERVAL`| `300.0`      | Upper bound for reconnect backoff (seconds)            |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `VELUX2MQTT_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### Logging

| Setting       | Env Variable                          | Default | Description                             |
| ------------- | ------------------------------------- | ------- | --------------------------------------- |
| Level         | `VELUX2MQTT_LOGGING__LEVEL`           | `INFO`  | Root log level                          |
| Format        | `VELUX2MQTT_LOGGING__FORMAT`          | `json`  | `json` or `text` output format          |
| File          | `VELUX2MQTT_LOGGING__FILE`            | ---     | Optional log file path                  |
| Max file size | `VELUX2MQTT_LOGGING__MAX_FILE_SIZE_MB`| `10`    | Max log file size in MB before rotation |
| Backup count  | `VELUX2MQTT_LOGGING__BACKUP_COUNT`    | `3`     | Number of rotated log files to keep     |

!!! tip "Choosing a log format"
    Use `json` (the default) for Docker and container environments --- structured logs
    are easier to parse with log aggregators. Use `text` for local development where
    human-readable output is more convenient.

### Cover Definitions

Covers are configured as a JSON list via the `VELUX2MQTT_COVERS` environment variable.
Each entry defines one cover (blind or window) with its GPIO pin mapping and travel
timing.

| Field                | Type    | Required | Default | Description                                                                 |
| -------------------- | ------- | -------- | ------- | --------------------------------------------------------------------------- |
| `name`               | string  | yes      | ---     | Unique cover identifier (e.g. `"blind"`, `"window"`)                        |
| `pin_up`             | int     | yes      | ---     | BCM GPIO pin for UP/OPEN button (0--27)                                     |
| `pin_stop`           | int     | yes      | ---     | BCM GPIO pin for STOP button (0--27)                                        |
| `pin_down`           | int     | yes      | ---     | BCM GPIO pin for DOWN/CLOSE button (0--27)                                  |
| `travel_duration_up` | float   | yes      | ---     | Seconds for full upward (open) travel                                       |
| `travel_duration_down`| float  | yes      | ---     | Seconds for full downward (close) travel                                    |
| `travel_time_offset` | float   | no       | `1.0`   | Seconds subtracted from elapsed time for motor start/stop lag               |
| `max_timer_margin`   | float   | no       | `2.0`   | Extra seconds added to travel duration for the safety cutoff timer          |
| `measure_offset`     | bool    | no       | `false` | Measure `travel_time_offset` during calibration instead of using the manual value |
| `dead_band_pct`      | float   | no       | `0.0`   | Percentage (0–<100) of total travel consumed by handle rotation before cover moves (0 disables) |

**Validation rules:**

- All three pins (`pin_up`, `pin_stop`, `pin_down`) must be distinct within a cover.
- Pins must not overlap across covers.
- Cover names must be unique.

#### Single-cover example

```bash
VELUX2MQTT_COVERS='[{"name": "blind", "pin_up": 9, "pin_stop": 10, "pin_down": 11, "travel_duration_up": 24.0, "travel_duration_down": 22.0}]'
```

#### Multi-cover example

```bash
VELUX2MQTT_COVERS='[
  {
    "name": "blind",
    "pin_up": 9,
    "pin_stop": 10,
    "pin_down": 11,
    "travel_duration_up": 24.0,
    "travel_duration_down": 22.0,
    "travel_time_offset": 0.8
  },
  {
    "name": "window",
    "pin_up": 23,
    "pin_stop": 24,
    "pin_down": 25,
    "travel_duration_up": 30.0,
    "travel_duration_down": 28.0,
    "measure_offset": true,
    "dead_band_pct": 5.0
  }
]'
```

!!! note "JSON in environment variables"
    The entire cover list is a single JSON value. In `.env` files, wrap it in single
    quotes. In Docker Compose, use YAML multiline syntax or escape as needed.

### Global GPIO Timing

| Setting              | Env Variable                        | Default | Description                                               |
| -------------------- | ----------------------------------- | ------- | --------------------------------------------------------- |
| Button press duration| `VELUX2MQTT_BUTTON_PRESS_DURATION`  | `0.5`   | Seconds to hold GPIO HIGH to simulate a button press      |

### Startup Homing

| Setting           | Env Variable                         | Default  | Description                                              |
| ----------------- | ------------------------------------ | -------- | -------------------------------------------------------- |
| Enable homing     | `VELUX2MQTT_ENABLE_STARTUP_HOMING`   | `true`   | Move covers to a known endpoint on startup               |
| Homing direction  | `VELUX2MQTT_HOMING_DIRECTION`        | `close`  | Direction to move during homing (`open` or `close`)      |

!!! tip "Why homing matters"
    Without a known starting position, the position tracker cannot calculate accurate
    percentages. Homing moves all covers to an endpoint (fully open or fully closed) on
    startup so the first position reading is reliable.

### Calibration

| Setting           | Env Variable                       | Default | Description                                                  |
| ----------------- | ---------------------------------- | ------- | ------------------------------------------------------------ |
| Calibration runs  | `VELUX2MQTT_CALIBRATION_RUNS`      | `3`     | Number of measurement runs per direction during calibration  |

### Drift Compensation

| Setting                    | Env Variable                              | Default | Description                                                                   |
| -------------------------- | ----------------------------------------- | ------- | ----------------------------------------------------------------------------- |
| Recalibration threshold    | `VELUX2MQTT_DRIFT_RECALIBRATION_THRESHOLD`| `2`     | After this many consecutive intermediate moves, recalibrate via an endpoint. 0 disables. |

!!! note "How drift compensation works"
    Position tracking accumulates small timing errors over multiple intermediate moves.
    When the threshold is reached, the next move automatically routes through an endpoint
    (0% or 100%) to reset the position tracker before continuing to the target.

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# velux2mqtt Configuration
# All settings can be set via environment variables with VELUX2MQTT_ prefix.
# Nested settings use __ delimiter (e.g., VELUX2MQTT_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
VELUX2MQTT_MQTT__HOST=localhost
VELUX2MQTT_MQTT__PORT=1883
# VELUX2MQTT_MQTT__USERNAME=
# VELUX2MQTT_MQTT__PASSWORD=
# VELUX2MQTT_MQTT__CLIENT_ID=velux2mqtt
# VELUX2MQTT_MQTT__TOPIC_PREFIX=velux2mqtt

# --- Logging ---
# VELUX2MQTT_LOGGING__LEVEL=INFO
# VELUX2MQTT_LOGGING__FORMAT=json

# --- Cover Definitions (JSON list) ---
# Each cover needs: name, pin_up, pin_stop, pin_down, travel_duration_up, travel_duration_down
VELUX2MQTT_COVERS='[{"name": "blind", "pin_up": 9, "pin_stop": 10, "pin_down": 11, "travel_duration_up": 24.0, "travel_duration_down": 22.0}]'

# --- Global GPIO Timing ---
# VELUX2MQTT_BUTTON_PRESS_DURATION=0.5

# --- Startup Homing ---
# VELUX2MQTT_ENABLE_STARTUP_HOMING=true
# VELUX2MQTT_HOMING_DIRECTION=close

# --- Calibration ---
# VELUX2MQTT_CALIBRATION_RUNS=3

# --- Drift Compensation ---
# VELUX2MQTT_DRIFT_RECALIBRATION_THRESHOLD=2
```

Uncomment and modify any line to override the default.

---

## Pydantic Settings

Under the hood, velux2mqtt extends the cosalette framework's `Settings` base class with
its own `Velux2MqttSettings`. This uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) which
provides:

- **Type validation** --- invalid values fail fast at startup with clear error messages
- **Multiple sources** --- environment variables, `.env` files, CLI flags, YAML, TOML
- **Nested models** --- MQTT settings are a sub-model, accessed via `__` delimiter

See the
[pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for advanced usage.
