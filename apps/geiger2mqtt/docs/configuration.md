# Configuration

geiger2mqtt uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration, giving you several ways to set any value:

1. **CLI flags** — highest priority
2. **Environment variables** — `GEIGER2MQTT_` prefix
3. **`.env` file** — loaded from the working directory
4. **Defaults** — built-in values

For most deployments, a `.env` file copied from `.env.example` is all you need.

---

## Settings Reference

### Geiger counter

| Setting           | Env Variable                     | Default          | Validation       | Description                                                  |
| ----------------- | -------------------------------- | ---------------- | ---------------- | ------------------------------------------------------------ |
| GPIO pin          | `GEIGER2MQTT_GPIO_PIN`           | `4`              | `>= 0`           | BCM number of the pin wired to the board output              |
| GPIO chip         | `GEIGER2MQTT_GPIO_CHIP`          | `/dev/gpiochip0` | starts with `/dev/` | Character device the health check tests for               |
| Pull-up           | `GEIGER2MQTT_GPIO_PULL_UP`       | `false`          | boolean          | Enable the Pi's internal pull-up; leave off when the board drives the line |
| Conversion factor | `GEIGER2MQTT_CONVERSION_FACTOR`  | `0.0057`         | `> 0`            | Dose rate in µSv/h per CPM; see [below](#conversion-factors) |
| Average window    | `GEIGER2MQTT_AVERAGE_WINDOW`     | `900`            | `>= 60`          | Seconds covered by `dose_rate_avg`                           |
| Publish interval  | `GEIGER2MQTT_PUBLISH_INTERVAL`   | `30`             | `> 0`            | Seconds between published readings                           |
| No-pulse timeout  | `GEIGER2MQTT_NO_PULSE_TIMEOUT`   | `300`            | `>= 0`           | Seconds without a pulse before the sensor goes offline; `0` disables the check |

`GEIGER2MQTT_GPIO_GID` (default `997`) is read by `compose.yml`, not by the app. See
[Getting Started](getting-started.md#gpio-access).

**How the readings are computed** ([ADR-001](adr/ADR-001-measurement-model.md)):

- `cpm` is the number of pulses in the last 60 seconds. The first reading comes 60
  seconds after the start.
- `dose_rate` is `cpm × conversion_factor`.
- `dose_rate_avg` counts the pulses in the last `AVERAGE_WINDOW` seconds and converts
  them to a rate per minute. Until that window has filled, it divides by the time
  counted so far, so the first readings are not biased low.

### Conversion factors

The factor converts counts per minute to µSv/h. It depends on the tube and on the
radiation it was calibrated against, so published values differ by tens of percent.
Treat the table as a starting point and calibrate against a reference instrument if
the absolute dose matters.

| Tube    | µSv/h per CPM | CPM per µSv/h | Source |
| ------- | ------------- | ------------- | ------ |
| SBM-20  | `0.0057`      | 175.43        | [DIYGeiger: GM tube info][diygeiger] (most cited value; the same page lists 150.51 for Co-60 and 98.58 for Cs-137) |
| J305β   | `0.0081`      | 123.15        | [IoT-devices: J305 conversion factor][j305] (commonly published 0.00812; the note derives 0.00332 from the current datasheet sensitivity of 44 CPS per mR/h for Co-60) |
| M4011   | `0.0065`      | 153.8         | [DIYGeiger: GM tube info][diygeiger] |
| SBM-19  | `0.0011`      | 875           | [DIYGeiger: GM tube info][diygeiger] (background radiation; 263 CPM per µSv/h for point sources) |
| LND 712 | `0.0081`      | 123.14        | [DIYGeiger: GM tube info][diygeiger] (commonly accepted; many users use 108, which is 0.0093) |

[diygeiger]: https://sites.google.com/site/diygeigercounter/technical/gm-tubes-supported
[j305]: https://iot-devices.com.ua/en/geiger-tube-j305-how-to-calculate-the-conversion-factor-of-cpm-technical-note-en/

### MQTT

| Setting            | Env Variable                               | Default                         | Description                                            |
| ------------------ | ------------------------------------------ | ------------------------------- | ------------------------------------------------------ |
| Host               | `GEIGER2MQTT_MQTT__HOST`                   | `localhost`                     | MQTT broker hostname (`mosquitto` in compose)          |
| Port               | `GEIGER2MQTT_MQTT__PORT`                   | `1883`                          | MQTT broker port                                       |
| Username           | `GEIGER2MQTT_MQTT__USERNAME`               | —                               | Broker username                                        |
| Password           | `GEIGER2MQTT_MQTT__PASSWORD`               | —                               | Broker password                                        |
| Client ID          | `GEIGER2MQTT_MQTT__CLIENT_ID`              | _(auto)_                        | MQTT client identifier                                 |
| Topic prefix       | `GEIGER2MQTT_MQTT__TOPIC_PREFIX`           | _(app name)_                    | Root prefix for all MQTT topics                        |
| Instance ID        | `GEIGER2MQTT_MQTT__INSTANCE_ID`            | _(app name)_                    | Home Assistant discovery identity; set a unique value per instance when several instances share a broker |
| Reconnect interval | `GEIGER2MQTT_MQTT__RECONNECT_INTERVAL`     | `5.0`                           | Initial reconnect delay (seconds, exponential backoff) |
| Reconnect max      | `GEIGER2MQTT_MQTT__RECONNECT_MAX_INTERVAL` | `300.0`                         | Upper bound for reconnect backoff (seconds)            |
| TLS                | `GEIGER2MQTT_MQTT__TLS`                    | `true` in code, `false` in compose | Broker TLS on port 8883; see below                  |
| Protocol version   | `GEIGER2MQTT_MQTT__PROTOCOL_VERSION`       | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry; see below         |
| Message expiry     | `GEIGER2MQTT_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400`                        | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |
| Verbose errors     | `GEIGER2MQTT_MQTT__ERROR_PUBLISH_VERBOSE`  | `false`                         | Publish full exception text on the error topics instead of the class name. Text may name hosts, devices or paths |

**TLS.** cosalette defaults to TLS. The bundled Mosquitto broker listens in plaintext
on the host's loopback interface, so `compose.yml` sets
`GEIGER2MQTT_MQTT__TLS=${GEIGER2MQTT_MQTT__TLS:-false}` and `.env.example` keeps
`false`. For a remote broker, set it to `true` together with
`GEIGER2MQTT_MQTT__TLS_CA_FILE` (and `TLS_CERT_FILE`/`TLS_KEY_FILE` for mutual TLS).
The decision is recorded in the monorepo's ADR-006.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects geiger2mqtt with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): state, availability, Home Assistant discovery, `_meta/*` and the
last will. While geiger2mqtt runs, it re-publishes each retained topic every third of
that interval, so the topics stay alive. A topic that nothing refreshes any more
disappears from the broker by itself. The decision is recorded in the monorepo's
ADR-009.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, geiger2mqtt logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `GEIGER2MQTT_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If geiger2mqtt is down or disconnected for
  longer than the expiry interval, the broker drops its retained topics until the next
  publish.
- **Consumers may see a repeat on refresh.** The repeat has the same payload as the last
  publish and arrives without the retain flag. The radiation state is published every
  `PUBLISH_INTERVAL` anyway, so a repeat looks like any other reading.

### Logging

| Setting       | Env Variable                            | Default | Description                             |
| ------------- | --------------------------------------- | ------- | --------------------------------------- |
| Level         | `GEIGER2MQTT_LOGGING__LEVEL`            | `INFO`  | Root log level                          |
| Format        | `GEIGER2MQTT_LOGGING__FORMAT`           | `json`  | `json` or `text` output format          |
| File          | `GEIGER2MQTT_LOGGING__FILE`             | —       | Optional log file path                  |
| Max file size | `GEIGER2MQTT_LOGGING__MAX_FILE_SIZE_MB` | `10`    | Max log file size in MB before rotation |
| Backup count  | `GEIGER2MQTT_LOGGING__BACKUP_COUNT`     | `3`     | Number of rotated log files to keep     |
| Levels        | `GEIGER2MQTT_LOGGING__LEVELS`           | `{}`    | Per-logger levels as JSON, e.g. `{"asyncio":"WARNING"}` |

### Health and recovery

MQTT is the primary health signal: the `geiger2mqtt/status` heartbeat and last will,
and the `geiger2mqtt/radiation/availability` topic (see [MQTT Topics](mqtt-topics.md)).
Recovery comes from process exits and the `restart: unless-stopped` policy in
`compose.yml`.

**No pulse is not stale.** When no pulse arrives for `NO_PULSE_TIMEOUT` seconds, the
radiation sensor goes offline and stays offline until the next pulse; the app keeps
running. The channel therefore opts out of cosalette's freshness watchdog
(`stale_after=None`). With the derived bound, every run without a pulse would count as
a failed cycle, the channel would turn `stale` after about 90 seconds, and an
`exit_after_stale` policy would restart the container every few minutes while the tube
is quiet. The handler only reads memory, so freshness has nothing else to detect: a
crashed task exits with code 4 and a blocked loop with code 6. geiger2mqtt therefore
sets no `exit_after_stale`.

**GPIO health check.** Every 30 seconds the adapter checks that `GPIO_CHIP` exists.
After five failed checks in a row, cosalette re-opens the pin, at most three times;
then the app exits.

**Loop-stall watchdog.** The GPIO callbacks run on lgpio's own thread, and the
event loop does no blocking I/O. `compose.yml` still sets
`COSALETTE_LOOP_STALL_TIMEOUT=120` as a backstop: after 120 seconds without a loop
turn, geiger2mqtt prints every thread's stack and exits with code 6. Set
`COSALETTE_LOOP_STALL_TIMEOUT` in the shell or `.env` to change the value.

**Docker health status.** The image sets `COSALETTE_HEALTH_FILE` and probes it with
`cosalette-health` every 60 seconds after a 90-second start period (60 seconds of
counting plus margin), so `docker ps` shows `healthy` or `unhealthy`. An `unhealthy`
status restarts nothing: the exit codes do. With a read-only root filesystem, mount a
tmpfs on `/tmp` for the health file.

| Exit code | Cause                                                                 |
| --------- | --------------------------------------------------------------------- |
| `1`       | Startup failure, or the event loop stalled while holding the GIL      |
| `3`       | Unexpected exception                                                  |
| `4`       | A framework task exhausted its restart budget                         |
| `6`       | The event loop did not run for `COSALETTE_LOOP_STALL_TIMEOUT` seconds |
