# Configuration

suncast uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
for configuration, giving you three ways to set any value:

1. **CLI flags** — highest priority
2. **Environment variables** — `SUNCAST_` prefix
3. **`.env` file** — loaded from the working directory
4. **Defaults** — built-in sensible values

Higher-priority sources override lower ones. For most deployments, a `.env` file is
all you need. See [`.env.example`](https://github.com/ff-fab/cosalette-apps/blob/main/apps/suncast/.env.example)
for a complete template.

---

## Settings Reference

### Location (Required)

| Setting     | Env Variable         | Default | Description                          |
| ----------- | -------------------- | ------- | ------------------------------------ |
| `latitude`  | `SUNCAST_LATITUDE`   | —       | GPS latitude (−90 to 90)            |
| `longitude` | `SUNCAST_LONGITUDE`  | —       | GPS longitude (−180 to 180)         |
| `timezone`  | `SUNCAST_TIMEZONE`   | —       | IANA timezone (e.g. `Europe/Berlin`) |

!!! warning "All three location settings are required"
    suncast cannot compute sun positions without a valid location. The app will
    refuse to start if any of these are missing.

### Geometry

| Setting         | Env Variable             | Default         | Description                          |
| --------------- | ------------------------ | --------------- | ------------------------------------ |
| `geometry_file` | `SUNCAST_GEOMETRY_FILE`  | `geometry.yaml` | Path to YAML/JSON geometry file      |

### Timing

| Setting         | Env Variable             | Default | Description                           |
| --------------- | ------------------------ | ------- | ------------------------------------- |
| `poll_interval` | `SUNCAST_POLL_INTERVAL`  | `360.0` | Seconds between render cycles (> 0)   |

### Rendering

| Setting           | Env Variable               | Default     | Description                                 |
| ----------------- | -------------------------- | ----------- | ------------------------------------------- |
| `primary_color`   | `SUNCAST_PRIMARY_COLOR`    | `#614c1f`   | Building fill color (dark/outline)          |
| `secondary_color` | `SUNCAST_SECONDARY_COLOR`  | `#b38c3a`   | Building accent color                       |
| `light_color`     | `SUNCAST_LIGHT_COLOR`      | `#f1b023`   | Sun and daylight arc color                  |
| `shadow_color`    | `SUNCAST_SHADOW_COLOR`     | `#2F3338`   | Shadow projection color                     |
| `stroke_width`    | `SUNCAST_STROKE_WIDTH`     | `1.0`       | SVG stroke width for building outlines      |
| `sundial_mode`    | `SUNCAST_SUNDIAL_MODE`     | `ring`      | Sundial display: `ring`, `compact`, or `off` |
| `marker_style`    | `SUNCAST_MARKER_STYLE`     | `circle`    | Hour marker style: `circle` or `bar`         |

#### Marker style comparison

<div class="geometry-comparison">
    <figure>
        <img src="../images/generated/marker-circle.svg" alt="Circle hour markers" width="250">
        <figcaption>
            <strong>Circle markers</strong>
            Default marker style with round hour indicators on the sundial ring.
        </figcaption>
    </figure>
    <figure>
        <img src="../images/generated/marker-bar.svg" alt="Bar hour markers" width="250">
        <figcaption>
            <strong>Bar markers</strong>
            Linear hour indicators for a more technical, gauge-like appearance.
        </figcaption>
    </figure>
</div>

#### Sundial mode comparison

<div class="geometry-comparison">
    <figure>
        <img src="../images/generated/sundial-ring.svg" alt="Sundial mode: ring" width="250">
        <figcaption>
            <strong>Ring</strong>
            Full 24-segment outer ring with hour markers and noon/midnight bars.
        </figcaption>
    </figure>
    <figure>
        <img src="../images/generated/sundial-compact.svg" alt="Sundial mode: compact" width="250">
        <figcaption>
            <strong>Compact</strong>
            Hour segments on the inner circle with a translucent daylight overlay.
        </figcaption>
    </figure>
    <figure>
        <img src="../images/generated/sundial-off.svg" alt="Sundial mode: off" width="250">
        <figcaption>
            <strong>Off</strong>
            Minimal view without any sundial elements, keeping only the core shadow rendering.
        </figcaption>
    </figure>
</div>

### Output

| Setting       | Env Variable            | Default   | Description                                            |
| ------------- | ----------------------- | --------- | ------------------------------------------------------ |
| `output_path` | `SUNCAST_OUTPUT_PATH`   | `/output` | Directory for SVG/PNG files. `null` to disable         |
| `png_enabled` | `SUNCAST_PNG_ENABLED`   | `false`   | Enable PNG rasterization (requires `suncast[png]`)     |
| `png_width`   | `SUNCAST_PNG_WIDTH`     | `800`     | PNG width in pixels (≥ 1)                              |
| `png_height`  | `SUNCAST_PNG_HEIGHT`    | `800`     | PNG height in pixels (≥ 1)                             |

### HTTP Server

| Setting        | Env Variable            | Default     | Description                    |
| -------------- | ----------------------- | ----------- | ------------------------------ |
| `http_enabled` | `SUNCAST_HTTP_ENABLED`  | `false`     | Enable built-in HTTP server    |
| `http_host`    | `SUNCAST_HTTP_HOST`     | `0.0.0.0`  | HTTP bind address              |
| `http_port`    | `SUNCAST_HTTP_PORT`     | `8080`      | HTTP port (1–65535)            |

!!! tip "HTTP server vs. nginx sidecar"
    The built-in HTTP server is an alternative for non-Docker deployments.
    In Docker, use the nginx sidecar pattern instead — see
    [Getting Started](getting-started.md).

### MQTT (Inherited)

MQTT settings are inherited from cosalette's `Settings` base class. See the
[cosalette docs](https://ff-fab.github.io/cosalette/) for the full reference.
Key settings:

| Setting         | Env Variable               | Default     | Description          |
| --------------- | -------------------------- | ----------- | -------------------- |
| `mqtt.host`     | `SUNCAST_MQTT__HOST`       | `localhost` | MQTT broker hostname |
| `mqtt.port`     | `SUNCAST_MQTT__PORT`       | `1883`      | MQTT broker port     |
| `mqtt.username` | `SUNCAST_MQTT__USERNAME`   | —           | MQTT username        |
| `mqtt.password` | `SUNCAST_MQTT__PASSWORD`   | —           | MQTT password        |
| `mqtt.topic_prefix` | `SUNCAST_MQTT__TOPIC_PREFIX` | `suncast` | Topic root; unique per instance on a shared broker |
| `mqtt.protocol_version` | `SUNCAST_MQTT__PROTOCOL_VERSION` | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below |
| `mqtt.message_expiry_interval` | `SUNCAST_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables
    use `__` (double underscore) to separate nesting levels:

    `SUNCAST_MQTT__HOST` → `settings.mqtt.host`

    This is a
    [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects suncast with MQTT 5. Every retained message it
publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): the SVG, the PNG, availability, `status`, `_meta/*` and the
last will. suncast publishes no Home Assistant discovery. While suncast runs, it
re-publishes each retained topic every third of that interval (default 8 hours), so the
topics stay alive. A topic that nothing refreshes any more, such as a renamed entity or
a stopped process, disappears from the broker by itself.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, suncast logs
  `does the broker support MQTT 5?` and retries the connection. Set
  `SUNCAST_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **A long outage lets topics expire.** If suncast is down or disconnected for longer
  than the expiry interval, the broker drops its retained topics until the next publish.
- **Consumers see one repeat per refresh.** The repeat replays the last image byte for
  byte, and the broker forwards it to live subscribers without the retain flag. The image
  is already replaced every `POLL_INTERVAL` (default 360 s), so a dashboard that shows
  `suncast/shadow/svg` or `suncast/shadow/png` sees no visible change.
- **The refresh ledger holds 16 MiB.** A retained publish that would exceed it fails, and
  suncast logs a warning and skips that image. The default SVG is about 5 KB.

### Health and recovery

MQTT is the primary health signal: the `suncast/status` heartbeat and last will, and
the `suncast/shadow/availability` topic (see [MQTT Topics](mqtt-topics.md)). Recovery
comes from process exits and the `restart: unless-stopped` policy in `compose.yml`.

**Freshness.** `shadow` is suncast's only entity. cosalette derives its freshness bound
from the poll interval and the implicit timeout of the same length:
`stale_after = 3 x SUNCAST_POLL_INTERVAL`, `1080` s (18 minutes) for the default 360 s.
The bound is three missed cycles: long enough that one slow or failed cycle never
flaps the entity, short enough that a dashboard image older than about 20 minutes is
flagged. It follows `SUNCAST_POLL_INTERVAL` without a separate setting.

A cycle counts as fresh when the handler returns. Output delivery is best effort: a
failed SVG or PNG file write (for example an unwritable `/output`), a failed PNG
rasterization or a failed MQTT publish logs a warning, and the cycle still counts.
Watch the logs for `Output delivery completed with N error(s)`. Only a handler that
keeps raising, a computation or render error, turns `shadow` `"stale"` in the heartbeat
and `offline`, and the built-in HTTP server keeps serving the last image.

A hung `/output` mount can outlast cosalette's implicit handler timeout (one poll
interval), cancelling that cycle with a `TimeoutError`. The worker thread cannot be
cancelled, so suncast keeps track of it and skips later file writes while it remains
stuck. This prevents repeated failures from filling the shared thread pool. MQTT
publishing runs before file output, so the retained state continues updating. The
files remain at their last successful version until the mount recovers or the process
restarts; watch for `Skipping filesystem output; previous write still running`
in the logs.

**No stale exit or restart.** suncast sets neither `exit_after_stale` nor
`restart_on_stale`. A failing cycle is a computation or render error on the same
geometry and settings, which a restart would repeat, or a hung `/output` mount, which
a restart does not unhang. suncast has no adapter, so there is nothing for
`restart_on_stale` to restart.

**Docker health status.** The image sets `COSALETTE_HEALTH_FILE` and probes it with
`cosalette-health` every 60 s, so `docker ps` shows `healthy` or `unhealthy`. With
`shadow` as the only entity, the probe keeps its default `--fail-on stale`: the
container turns `unhealthy` when `shadow` is stale or the health file is older than
180 s. An `unhealthy` status restarts nothing: the exit codes below do. With a
read-only root filesystem, mount a tmpfs on `/tmp` for the health file.

**Loop-stall watchdog.** PNG rasterization (about 200 ms with CairoSVG) and the file
writes run in a worker thread, off the event loop. Solar position, shadow computation
and SVG rendering still run on the loop, for about 50 ms per cycle. A hung file write
does not wedge the loop; suncast skips subsequent writes while the worker remains
stuck. As a backstop against any other wedge, `compose.yml` sets
`COSALETTE_LOOP_STALL_TIMEOUT` to `120` seconds: if the loop does not run for that
long, cosalette prints thread stacks and exits with code 6, after which
`restart: unless-stopped` recovers the process. Set the variable in the shell or `.env`
to override the value.

| Exit code | Cause                                                                 |
| --------- | --------------------------------------------------------------------- |
| `1`       | Startup failure                                                       |
| `3`       | Unexpected exception                                                  |
| `4`       | A framework task exhausted its restart budget                         |
| `6`       | The event loop did not run for `COSALETTE_LOOP_STALL_TIMEOUT` seconds |

**Several locations on one broker.** Give each suncast instance its own
`SUNCAST_MQTT__TOPIC_PREFIX`. suncast publishes no Home Assistant discovery, so
`SUNCAST_MQTT__INSTANCE_ID` has no effect and needs no value.

**Log redaction.** suncast does not set `App(redact=)`. No secret reaches log or error
text: the only credential is the MQTT password, a `SecretStr`. Logs carry file paths
and the configured location.

---

## `.env` Example

Copy the provided template and edit to taste:

```bash
cp .env.example .env
```

```dotenv title=".env.example"
# suncast Configuration
# All settings can be set via environment variables with SUNCAST_ prefix.
# Nested settings use __ delimiter (e.g., SUNCAST_MQTT__HOST).

# --- MQTT Settings (cosalette base) ---
SUNCAST_MQTT__HOST=localhost
# Broker terminates plaintext MQTT; see docs/adr/ADR-006.
SUNCAST_MQTT__TLS=false
# MQTT 5 retained-message expiry; the bundled mosquitto:2 supports it.
# Set to 3.1.1 for a broker without MQTT 5; see docs/adr/ADR-009.
SUNCAST_MQTT__PROTOCOL_VERSION=5
# SUNCAST_MQTT__MESSAGE_EXPIRY_INTERVAL=86400
SUNCAST_MQTT__PORT=1883
# SUNCAST_MQTT__USERNAME=
# SUNCAST_MQTT__PASSWORD=

# --- Location (required) ---
SUNCAST_LATITUDE=48.1351
SUNCAST_LONGITUDE=11.5820
SUNCAST_TIMEZONE=Europe/Berlin

# --- Geometry ---
# SUNCAST_GEOMETRY_FILE=geometry.yaml

# --- Polling ---
# SUNCAST_POLL_INTERVAL=360.0

# --- Rendering ---
# SUNCAST_PRIMARY_COLOR=#614c1f
# SUNCAST_SECONDARY_COLOR=#b38c3a
# SUNCAST_LIGHT_COLOR=#f1b023
# SUNCAST_SHADOW_COLOR=#2F3338
# SUNCAST_STROKE_WIDTH=1.0
# SUNCAST_SUNDIAL_MODE=ring
# SUNCAST_MARKER_STYLE=circle

# --- Output ---
# SUNCAST_OUTPUT_PATH=/output
# SUNCAST_PNG_ENABLED=false
# SUNCAST_PNG_WIDTH=800
# SUNCAST_PNG_HEIGHT=800

# --- HTTP Server ---
# SUNCAST_HTTP_ENABLED=false
# SUNCAST_HTTP_HOST=0.0.0.0
# SUNCAST_HTTP_PORT=8080

# --- Health (read by compose.yml; see docs/configuration.md) ---
# Seconds without an event-loop turn before exit code 6.
# COSALETTE_LOOP_STALL_TIMEOUT=120
```
