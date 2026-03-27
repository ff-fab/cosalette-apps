# Configuration

caldates2mqtt uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration. Values can come from three sources that override built-in defaults:

1. **CLI flags** --- highest priority
2. **Environment variables** --- `CALDATES2MQTT_` prefix
3. **`.env` file** --- loaded from the working directory

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting            | Env Variable                                | Default      | Description                                            |
| ------------------ | ------------------------------------------- | ------------ | ------------------------------------------------------ |
| Host               | `CALDATES2MQTT_MQTT__HOST`                  | `localhost`  | MQTT broker hostname                                   |
| Port               | `CALDATES2MQTT_MQTT__PORT`                  | `1883`       | MQTT broker port                                       |
| Username           | `CALDATES2MQTT_MQTT__USERNAME`              | ---          | Broker username                                        |
| Password           | `CALDATES2MQTT_MQTT__PASSWORD`              | ---          | Broker password                                        |
| Client ID          | `CALDATES2MQTT_MQTT__CLIENT_ID`             | _(auto)_     | MQTT client identifier (auto-generated if empty)       |
| Topic prefix       | `CALDATES2MQTT_MQTT__TOPIC_PREFIX`          | _(app name)_ | Root prefix for all MQTT topics                        |
| Reconnect interval | `CALDATES2MQTT_MQTT__RECONNECT_INTERVAL`    | `5.0`        | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `CALDATES2MQTT_MQTT__RECONNECT_MAX_INTERVAL`| `300.0`      | Upper bound for reconnect backoff (seconds)            |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `CALDATES2MQTT_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### Logging

| Setting       | Env Variable                              | Default | Description                             |
| ------------- | ----------------------------------------- | ------- | --------------------------------------- |
| Level         | `CALDATES2MQTT_LOGGING__LEVEL`            | `INFO`  | Root log level                          |
| Format        | `CALDATES2MQTT_LOGGING__FORMAT`           | `json`  | `json` or `text` output format          |
| File          | `CALDATES2MQTT_LOGGING__FILE`             | ---     | Optional log file path                  |
| Max file size | `CALDATES2MQTT_LOGGING__MAX_FILE_SIZE_MB` | `10`    | Max log file size in MB before rotation |
| Backup count  | `CALDATES2MQTT_LOGGING__BACKUP_COUNT`     | `3`     | Number of rotated log files to keep     |

!!! tip "Choosing a log format"
    Use `json` (the default) for Docker and container environments --- structured logs
    are easier to parse with log aggregators. Use `text` for local development where
    human-readable output is more convenient.

### CalDAV

| Setting         | Env Variable                 | Default | Description                          |
| --------------- | ---------------------------- | ------- | ------------------------------------ |
| Calendars       | `CALDATES2MQTT_CALENDARS`    | _(required)_ | JSON list of calendar configurations |
| CalDAV timeout  | `CALDATES2MQTT_CALDAV_TIMEOUT`| `30.0` | HTTP timeout for CalDAV requests (seconds) |

### Per-Calendar Settings

Each entry in the `CALDATES2MQTT_CALENDARS` JSON list supports these fields:

| Field           | Type     | Required | Default | Description                                      |
| --------------- | -------- | -------- | ------- | ------------------------------------------------ |
| `key`           | string   | yes      | ---     | Unique identifier, used as MQTT device name      |
| `url`           | string   | yes      | ---     | CalDAV server URL                                |
| `calendar_name` | string   | yes      | ---     | Calendar name (path segment) on the server       |
| `username`      | string   | yes      | ---     | CalDAV auth username                             |
| `password`      | string   | yes      | ---     | CalDAV auth password                             |
| `entries`       | integer  | no       | `5`     | Number of upcoming events to fetch               |
| `days`          | integer  | no       | `14`    | Lookahead window in days                         |
| `poll_interval` | float    | no       | `7200`  | Seconds between reads (default 2 hours)          |

!!! note "Calendar key uniqueness"
    Each calendar's `key` must be unique --- it becomes the MQTT device name and topic
    segment. For example, `"key": "garbage"` publishes to `caldates2mqtt/garbage/state`.

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# caldates2mqtt Configuration
# All settings can be set via environment variables with CALDATES2MQTT_ prefix.
# Nested settings use __ delimiter (e.g., CALDATES2MQTT_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
CALDATES2MQTT_MQTT__HOST=localhost
CALDATES2MQTT_MQTT__PORT=1883
# CALDATES2MQTT_MQTT__USERNAME=
# CALDATES2MQTT_MQTT__PASSWORD=
# CALDATES2MQTT_MQTT__CLIENT_ID=caldates2mqtt
# CALDATES2MQTT_MQTT__TOPIC_PREFIX=caldates2mqtt

# --- Logging ---
# CALDATES2MQTT_LOGGING__LEVEL=INFO
# CALDATES2MQTT_LOGGING__FORMAT=json

# --- CalDAV Calendars ---
# REQUIRED: JSON list of calendar configurations
# Each calendar becomes its own MQTT device with periodic polling.
CALDATES2MQTT_CALENDARS='[{"key":"garbage","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"abfall_shared_by_fab","username":"user","password":"secret","entries":5,"days":14,"poll_interval":7200},{"key":"birthday","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"birthdays","username":"user","password":"secret"}]'

# HTTP timeout for CalDAV requests in seconds (default: 30)
# CALDATES2MQTT_CALDAV_TIMEOUT=30
```

Uncomment and modify any line to override the default.

---

## Multi-Calendar Example

A typical Nextcloud setup with garbage collection and birthday calendars:

```dotenv title=".env"
CALDATES2MQTT_MQTT__HOST=192.168.1.100

CALDATES2MQTT_CALENDARS='[
  {
    "key": "garbage",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "abfall_shared_by_fab",
    "username": "user",
    "password": "secret",
    "entries": 5,
    "days": 14,
    "poll_interval": 7200
  },
  {
    "key": "birthday",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "birthdays",
    "username": "user",
    "password": "secret",
    "entries": 10,
    "days": 30,
    "poll_interval": 86400
  }
]'
```

!!! tip "JSON formatting"
    The `CALDATES2MQTT_CALENDARS` value must be valid JSON. For readability in `.env`
    files, you can use multi-line values with single quotes as shown above. In
    `docker-compose.yml` environment sections, keep it on a single line.

---

## Pydantic Settings

Under the hood, caldates2mqtt extends the cosalette framework's `Settings` base class
with its own `CalDates2MqttSettings`. This uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) which
provides:

- **Type validation** --- invalid values fail fast at startup with clear error messages
- **Multiple sources** --- environment variables, `.env` files, CLI flags, YAML, TOML
- **Nested models** --- MQTT settings are a sub-model, accessed via `__` delimiter

See the
[pydantic-settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for advanced usage.
