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
| Instance ID | `CALDATES2MQTT_MQTT__INSTANCE_ID` | _(app name)_ | Home Assistant discovery identity; set a unique value per instance when several instances share a broker |
| Reconnect interval | `CALDATES2MQTT_MQTT__RECONNECT_INTERVAL`    | `5.0`        | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `CALDATES2MQTT_MQTT__RECONNECT_MAX_INTERVAL`| `300.0`      | Upper bound for reconnect backoff (seconds)            |
| Protocol version   | `CALDATES2MQTT_MQTT__PROTOCOL_VERSION` | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below |
| Message expiry     | `CALDATES2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate the nesting levels:

    `CALDATES2MQTT_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects caldates2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): state, availability, Home Assistant discovery, `_meta/*`
and the last will. While caldates2mqtt runs, it re-publishes each retained topic every third
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

- **There is no automatic fallback.** If the broker refuses MQTT 5, caldates2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `CALDATES2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If caldates2mqtt is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics until the next publish.
- **Consumers see one repeat per refresh.** The repeat has the same payload as the last
  publish, and the broker forwards it to live subscribers without the retain flag, so it
  looks like a normal message. Home Assistant sensors do not change state on a repeat.
  `caldates2mqtt/<calendar>/state` is republished on every calendar schedule run, and the
  refresh adds one identical repeat every 8 hours. An automation with an MQTT trigger
  on that topic runs for the repeat; an automation on the Home Assistant event count
  sensor does not, because the value does not change.

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
| Trigger min interval | `CALDATES2MQTT_TRIGGER_MIN_INTERVAL` | `60.0` | Minimum seconds between on-demand `/set` re-fetches |

!!! note "Trigger throttle (`TRIGGER_MIN_INTERVAL`)"
    `caldates2mqtt/{calendar}/set` is a public MQTT topic that forces an on-demand
    re-fetch, and each wake is a full CalDAV round-trip against a third-party server.
    This throttle is the minimum spacing (seconds) between two such trigger-initiated
    fetches, so a stuck automation cannot turn into a request flood. A wake that arrives
    inside a closed window is **held, not dropped**. **Raise it** for a stricter or
    shared CalDAV server that rate-limits; **lower it** for snappier on-demand refreshes
    at the cost of more server load. It is enforced per calendar and is independent of
    each calendar's `schedule` cron cadence. Must be `> 0`.

### Per-Calendar Settings

Each entry in the `CALDATES2MQTT_CALENDARS` JSON list supports these fields:

| Field           | Type     | Required | Default | Description                                      |
| --------------- | -------- | -------- | ------- | ------------------------------------------------ |
| `key`           | string   | yes      | ---     | Unique identifier, used as MQTT device name      |
| `url`           | string   | yes      | ---     | CalDAV server URL                                |
| `calendar_name` | string   | yes      | ---     | Calendar name (path segment) on the server       |
| `username`      | string   | yes      | ---     | CalDAV auth username                             |
| `password`      | string   | yes      | ---     | CalDAV auth password                             |
| `entries`       | integer  | no       | `5`     | Number of upcoming events to fetch (1 to 50)     |
| `days`          | integer  | no       | `14`    | Lookahead window in days (1 to 365)              |
| `schedule`      | string   | no       | `"0 0 0/2 * * ?"` | Quartz cron expression for polling schedule (default: every 2 hours) |

!!! note "Calendar key uniqueness"
    Each calendar's `key` must be unique --- it becomes the MQTT device name and topic
    segment. For example, `"key": "garbage"` publishes to `caldates2mqtt/garbage/state`.

### Health and recovery

MQTT is the primary health signal: the `caldates2mqtt/status` heartbeat and last will,
and each calendar's `availability` topic (see [MQTT Topics](mqtt-topics.md)). Recovery
comes from process exits and the `restart: unless-stopped` policy in `compose.yml`.

**Freshness.** Each calendar uses the `stale_after` bound that cosalette derives from
the longest gap in its `schedule`: `2 x gap + 72 x 3`. A cron schedule has no handler
timeout, and each of the 3 retries adds up to 72 s of backoff (the 60 s backoff cap
plus 20 % jitter). A read that returns the same events, or a `/set` re-read, also
counts as fresh.

| `schedule`               | Longest gap | Derived `stale_after`  |
| ------------------------ | ----------- | ---------------------- |
| `0 0 0/2 * * ?` (default) | 2 h        | 14616 s (about 4 h 4 min)  |
| `0 0 6 * * ?` (daily)    | 24 h        | 173016 s (about 48 h 4 min) |

A calendar is therefore stale only after two scheduled reads in a row fail. The
`stale_after` allowance includes the framework's retry backoff, but it is not a hard
upper bound on a CalDAV read: `date_search` can be followed by an HTTP request for each
event without inline data, so a read can make multiple requests. The configured
`CALDATES2MQTT_CALDAV_TIMEOUT` applies per request.

**No exit after stale.** caldates2mqtt sets neither `exit_after_stale` nor
`restart_on_stale`. The reader opens a new connection for every read, so a restart
cannot repair a stale calendar: the cause is the server, the network or the
credentials. One stale calendar would also restart all the other calendars. A stale
calendar stays `offline` on MQTT and marks the container `unhealthy` until a read
succeeds.

**Loop-stall watchdog.** The CalDAV requests run in a worker thread, so nothing should
block the event loop. `compose.yml` sets `COSALETTE_LOOP_STALL_TIMEOUT` to `300`
seconds as a guard against a defect. After 300 s without a loop turn, caldates2mqtt
prints every thread's stack and exits with code 6. Set `COSALETTE_LOOP_STALL_TIMEOUT`
in the shell or `.env` to change the value; remove the line from `compose.yml` to
disable the watchdog.

**Docker health status.** The image sets `COSALETTE_HEALTH_FILE` and probes it with
`cosalette-health --fail-on ""` every 60 s, so `docker ps` shows `healthy` or `unhealthy`.
This checks probe-file freshness without making one stale calendar mark the whole
container unhealthy. A stale calendar remains visible through MQTT; the container
status turns `unhealthy` when the health file is older than 180 s. An `unhealthy`
status restarts nothing: the exit codes below do. With a read-only root filesystem,
mount a tmpfs on `/tmp` for the health file.

| Exit code | Cause                                                                 |
| --------- | --------------------------------------------------------------------- |
| `1`       | Startup failure, or the event loop stalled while holding the GIL      |
| `3`       | Unexpected exception                                                  |
| `4`       | A framework task exhausted its restart budget                         |
| `6`       | The event loop did not run for `COSALETTE_LOOP_STALL_TIMEOUT` seconds |

**Several accounts.** One instance reads any number of calendars from any number of
servers and accounts, because each calendar has its own `url`, `username` and
`password`. Run one instance per broker. If a second instance shares the broker, give
each its own `CALDATES2MQTT_MQTT__TOPIC_PREFIX` and `CALDATES2MQTT_MQTT__INSTANCE_ID`.
Setting the instance ID changes the Home Assistant unique IDs once, so set it before
the first start.

**Log redaction.** caldates2mqtt does not set `App(redact=)`. Passwords go only into
the HTTP authentication, caldav removes user information from URLs, and error
messages carry only the scheme, host, path and calendar name.

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
# Broker terminates plaintext MQTT; see docs/adr/ADR-006.
CALDATES2MQTT_MQTT__TLS=false
# MQTT 5 retained-message expiry; the bundled mosquitto:2 supports it.
# Set to 3.1.1 for a broker without MQTT 5; see docs/adr/ADR-009.
CALDATES2MQTT_MQTT__PROTOCOL_VERSION=5
# CALDATES2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL=86400
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
CALDATES2MQTT_CALENDARS='[{"key":"garbage","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"abfall_shared_by_fab","username":"user","password":"secret","entries":5,"days":14,"schedule":"0 0 0/2 * * ?"},{"key":"birthday","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"birthdays","username":"user","password":"secret"}]'

# HTTP timeout for CalDAV requests in seconds (default: 30)
# CALDATES2MQTT_CALDAV_TIMEOUT=30

# Minimum seconds between on-demand /set re-fetches, must be > 0 (default: 60).
# Raise for a stricter/shared CalDAV server; lower for snappier refreshes.
# CALDATES2MQTT_TRIGGER_MIN_INTERVAL=60

# Store path for persisting state across restarts (default: XDG_STATE_HOME)
# CALDATES2MQTT_STORE_PATH=/app/data/store.json

# --- Health (read by compose.yml; see docs/configuration.md) ---
# Seconds without an event-loop turn before exit code 6.
# COSALETTE_LOOP_STALL_TIMEOUT=300
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
    "schedule": "0 0 0/2 * * ?"
  },
  {
    "key": "birthday",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "birthdays",
    "username": "user",
    "password": "secret",
    "entries": 10,
    "days": 30,
    "schedule": "0 0 6 * * ?"
  }
]'
```

!!! tip "JSON formatting"
    The `CALDATES2MQTT_CALENDARS` value must be valid JSON. For readability in `.env`
    files, you can use multi-line values with single quotes as shown above. In
    `compose.yml` environment sections, keep it on a single line.

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
