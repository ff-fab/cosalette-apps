# Configuration

gas2mqtt uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration, giving you three ways to set any value:

1. **CLI flags** — highest priority
2. **Environment variables** — `GAS2MQTT_` prefix
3. **`.env` file** — loaded from the working directory
4. **Defaults** — built-in sensible values

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting            | Env Variable                            | Default      | Description                                            |
| ------------------ | --------------------------------------- | ------------ | ------------------------------------------------------ |
| Host               | `GAS2MQTT_MQTT__HOST`                   | `localhost`  | MQTT broker hostname                                   |
| Port               | `GAS2MQTT_MQTT__PORT`                   | `1883`       | MQTT broker port                                       |
| Username           | `GAS2MQTT_MQTT__USERNAME`               | —            | Broker username                                        |
| Password           | `GAS2MQTT_MQTT__PASSWORD`               | —            | Broker password                                        |
| Client ID          | `GAS2MQTT_MQTT__CLIENT_ID`              | _(auto)_     | MQTT client identifier (auto-generated if empty)       |
| Topic prefix       | `GAS2MQTT_MQTT__TOPIC_PREFIX`           | _(app name)_ | Root prefix for all MQTT topics                        |
| Reconnect interval | `GAS2MQTT_MQTT__RECONNECT_INTERVAL`     | `5.0`        | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `GAS2MQTT_MQTT__RECONNECT_MAX_INTERVAL` | `300.0`      | Upper bound for reconnect backoff (seconds)            |
| Protocol version   | `GAS2MQTT_MQTT__PROTOCOL_VERSION` | `3.1.1` | `5` enables retained-message expiry (compose default), see below |
| Message expiry     | `GAS2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400` | Expiry of retained messages in seconds (MQTT 5 only) |

!!! info "Double-underscore delimiter" MQTT settings are **nested** inside the settings
model. Environment variables use `__` (double underscore) to separate the nesting
levels:

    `GAS2MQTT_MQTT__HOST` → `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects gas2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): state, availability, Home Assistant discovery, `_meta/*`
and the last will. While gas2mqtt runs, it re-publishes each retained topic every third
of that interval (default 8 hours), so the topics stay alive. A topic that nothing
refreshes any more, such as a renamed entity or a stopped process, disappears from the
broker by itself.

| Setting         | Env Variable                          | Default                          | Description                                                  |
| --------------- | ------------------------------------- | -------------------------------- | ------------------------------------------------------------ |
| Protocol        | `GAS2MQTT_MQTT__PROTOCOL_VERSION`         | `3.1.1` in code, `5` in compose  | `5` enables expiry and refresh, `3.1.1` disables both        |
| Expiry interval | `GAS2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL`  | `86400`                          | Seconds, at least `3`; valid only with protocol `5`          |

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, gas2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `GAS2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If gas2mqtt is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics until the next publish.
- **Consumers see one repeat per refresh.** The repeat has the same payload as the last
  publish, and the broker forwards it to live subscribers without the retain flag, so it
  looks like a normal message. Home Assistant sensors do not change state on a repeat.
  `gas2mqtt/gas_counter/state` is published only when the trigger changes, so
the refresh is the only repeat of the last tick. A consumer that counts MQTT
messages as pulses (for example an openHAB rule on "received update") counts one
extra pulse per refresh. Use the cumulative `counter` or `consumption_m3` value
instead: both are identical in the repeat.

### Logging

| Setting       | Env Variable                         | Default | Description                             |
| ------------- | ------------------------------------ | ------- | --------------------------------------- |
| Level         | `GAS2MQTT_LOGGING__LEVEL`            | `INFO`  | Root log level                          |
| Format        | `GAS2MQTT_LOGGING__FORMAT`           | `json`  | `json` or `text` output format          |
| File          | `GAS2MQTT_LOGGING__FILE`             | —       | Optional log file path                  |
| Max file size | `GAS2MQTT_LOGGING__MAX_FILE_SIZE_MB` | `10`    | Max log file size in MB before rotation |
| Backup count  | `GAS2MQTT_LOGGING__BACKUP_COUNT`     | `3`     | Number of rotated log files to keep     |

!!! tip "Choosing a log format" Use `json` (the default) for Docker and container
environments — structured logs are easier to parse with log aggregators. Use `text` for
local development where human-readable output is more convenient.

### I2C / Sensor

| Setting     | Env Variable           | Default     | Description                    |
| ----------- | ---------------------- | ----------- | ------------------------------ |
| I2C bus     | `GAS2MQTT_I2C_BUS`     | `1`         | I2C bus number                 |
| I2C address | `GAS2MQTT_I2C_ADDRESS` | `13` (0x0D) | QMC5883L I2C address (decimal) |

### Schmitt Trigger

| Setting       | Env Variable                  | Default | Description                       |
| ------------- | ----------------------------- | ------- | --------------------------------- |
| Trigger level | `GAS2MQTT_TRIGGER_LEVEL`      | `-5000` | Bz centre threshold               |
| Hysteresis    | `GAS2MQTT_TRIGGER_HYSTERESIS` | `700`   | Dead-band half-width around level |

!!! tip "Calibrating the trigger" Enable the debug magnetometer device
(`GAS2MQTT_ENABLE_DEBUG_DEVICE=true`) to see raw Bz values. Observe the range as the gas
meter rotates, then set the trigger level to the midpoint and hysteresis to half the
swing.

!!! note "Switching thresholds" The Schmitt trigger uses two thresholds derived from
your settings:

    - **Upper threshold** = `trigger_level + trigger_hysteresis`
    - **Lower threshold** = `trigger_level − trigger_hysteresis`

    With defaults (`-5000` / `700`), the trigger closes at **−4300** and opens at
    **−5700**.

### Polling

| Setting              | Env Variable                    | Default | Description                            |
| -------------------- | ------------------------------- | ------- | -------------------------------------- |
| Poll interval        | `GAS2MQTT_POLL_INTERVAL`        | `1.0`   | Gas counter polling interval (seconds) |
| Temperature interval | `GAS2MQTT_TEMPERATURE_INTERVAL` | `300.0` | Temperature report interval (seconds)  |

### Temperature Calibration

| Setting       | Env Variable             | Default  | Description                                           |
| ------------- | ------------------------ | -------- | ----------------------------------------------------- |
| Scale         | `GAS2MQTT_TEMP_SCALE`    | `0.008`  | Calibration scale factor                              |
| Offset        | `GAS2MQTT_TEMP_OFFSET`   | `20.3`   | Calibration offset (°C)                               |
| Smoothing tau | `GAS2MQTT_SMOOTHING_TAU` | `1200.0` | PT1 filter time constant (seconds, higher = smoother) |

The QMC5883L has a built-in temperature sensor. gas2mqtt applies an empirical linear
calibration: `temp_celsius = temp_scale × raw + temp_offset`. The PT1 filter smooths
readings to reduce noise. The time constant (τ) controls responsiveness — higher values
produce smoother, slower-reacting output. With the default τ=1200s and polling interval
of 300s, the effective smoothing factor is 0.2.

### Optional Features

| Setting              | Env Variable                           | Default | Description                    |
| -------------------- | -------------------------------------- | ------- | ------------------------------ |
| Consumption tracking | `GAS2MQTT_ENABLE_CONSUMPTION_TRACKING` | `false` | Enable cumulative m³ tracking  |
| Liters per tick      | `GAS2MQTT_LITERS_PER_TICK`             | `10.0`  | Gas liters per counter tick    |
| Debug device         | `GAS2MQTT_ENABLE_DEBUG_DEVICE`         | `false` | Enable raw magnetometer output |

### State Persistence

| Setting    | Env Variable          | Default    | Description                                    |
| ---------- | --------------------- | ---------- | ---------------------------------------------- |
| State file | `GAS2MQTT_STATE_FILE` | XDG path   | Optional path override for persisted device state |

By default, gas2mqtt saves gas counter ticks and consumption data to the XDG state path:
`$XDG_STATE_HOME/gas2mqtt/state.json` or `~/.local/state/gas2mqtt/state.json`.
Set `GAS2MQTT_STATE_FILE` to override that location explicitly.

!!! tip "Docker deployments" The `compose.yml` maps a `gas2mqtt-data` volume to
`/app/data`. Set `GAS2MQTT_STATE_FILE=/app/data/state.json` in your `.env` to persist
state across container restarts.

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
# Broker terminates plaintext MQTT; see docs/adr/ADR-006.
GAS2MQTT_MQTT__TLS=false
# MQTT 5 retained-message expiry; the bundled mosquitto:2 supports it.
# Set to 3.1.1 for a broker without MQTT 5; see docs/adr/ADR-009.
GAS2MQTT_MQTT__PROTOCOL_VERSION=5
# GAS2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL=86400
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
# GAS2MQTT_SMOOTHING_TAU=1200.0

# --- Consumption Tracking ---
# GAS2MQTT_ENABLE_CONSUMPTION_TRACKING=false
# GAS2MQTT_LITERS_PER_TICK=10.0

# --- State Persistence ---
# Persist counter and consumption across restarts.
# Default: $XDG_STATE_HOME/gas2mqtt/state.json or ~/.local/state/gas2mqtt/state.json
# Override for Docker volume mounts:
# GAS2MQTT_STATE_FILE=/app/data/state.json

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

See the
[pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for advanced usage.
