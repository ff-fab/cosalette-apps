# Operations

Deployment, monitoring, persistence, and logging configuration.

---

## Docker Deployment

The Docker files live in `apps/jeelink2mqtt/`:

- **Dockerfile** — multi-stage build using `uv` for fast dependency resolution
- **compose.yml** — full stack with Mosquitto MQTT broker

### Build and Run

```bash
docker compose -f apps/jeelink2mqtt/compose.yml up -d
```

To run in dry-run mode (no hardware or MQTT required):

```bash
docker compose -f apps/jeelink2mqtt/compose.yml run --rm jeelink2mqtt --dry-run
```

### Configuration

Environment variables are set in `compose.yml`.  Edit them
directly or override with a `.env` file alongside the compose file.
See [Reference](reference.md) for the full list of settings.

!!! warning "Device passthrough"

    The `devices` section passes the USB serial device into the container.
    If the device path changes (e.g. after a reboot), update the mapping
    or use a udev rule to create a stable symlink.

---

## systemd Service

### Unit File

```ini
# /etc/systemd/system/jeelink2mqtt.service
[Unit]
Description=JeeLink LaCrosse MQTT bridge
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=jeelink
Group=dialout
WorkingDirectory=/opt/jeelink2mqtt
EnvironmentFile=/opt/jeelink2mqtt/.env
ExecStart=/opt/jeelink2mqtt/.venv/bin/jeelink2mqtt
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Management Commands

```bash
# Enable and start
sudo systemctl enable --now jeelink2mqtt

# Follow logs
journalctl -u jeelink2mqtt -f

# Restart after config change
sudo systemctl restart jeelink2mqtt
```

---

## Monitoring

### Per-Sensor Availability

Subscribe to availability topics to detect sensor outages:

```bash
mosquitto_sub -h localhost -t 'jeelink2mqtt/+/availability' -v
```

Each sensor publishes a retained availability message:

- `"online"` — readings are flowing within the staleness timeout
- `"offline"` — no reading received within the staleness timeout

### Staleness Detection

Sensors are marked offline after exceeding their staleness timeout:

| Setting | Default | Description |
|---------|---------|-------------|
| Global: `staleness_timeout_seconds` | 600 s (10 min) | Applied to all sensors |
| Per-sensor: `staleness_timeout` | `null` (use global) | Override per sensor |

### Mapping Events

Subscribe to mapping change notifications:

```bash
mosquitto_sub -h localhost -t 'jeelink2mqtt/mapping/event' -v
```

Events include `auto_adopt`, `manual_assign`, `manual_reset`, and
`reset_all` — useful for alerting on unexpected battery swaps.

### Heartbeat

Even when readings haven't changed, jeelink2mqtt re-publishes the last
known state every `heartbeat_interval_seconds` (default: 180 s).  This
ensures downstream systems don't erroneously mark sensors as stale when
the environment is stable.

---

## Health and recovery

MQTT is the primary health signal: the retained `jeelink2mqtt/status` heartbeat and last
will, and each sensor's `availability` topic. Recovery comes from process exits and the
`restart: unless-stopped` policy in `compose.yml`.

**Status heartbeat.** cosalette publishes `jeelink2mqtt/status` every 60 s. Its
`devices.receiver` entry describes the serial receiver: `status` (`"ok"` or `"stale"`),
`last_success_at` (the time of the last decoded frame) and `consecutive_failures`. The
per-sensor entries describe the sensor devices; their availability follows the
[staleness timeout](#staleness-detection).

**Receiver freshness.** Every decoded frame keeps the receiver fresh, from any LaCrosse
sensor in range, also from sensors that are not mapped. The receiver turns `"stale"` when
no frame arrives for the longest configured staleness timeout: the larger of
`staleness_timeout_seconds` and every per-sensor `staleness_timeout` (600 s by
default). A stale receiver means that the JeeLink, its USB connection or the reader
thread is dead, not one sensor.

The receiver is a root stream, so it has no `availability` topic and sets no `feeds=`.
A name would move `raw/state` and `mapping/*` under `jeelink2mqtt/receiver/`. Each
sensor already goes `offline` through its own staleness timeout when frames stop.

**Exit after stale.** When the receiver stays `"stale"` for 300 s, jeelink2mqtt logs a
`CRITICAL` line and exits with code 5. The restart opens the serial port again and starts
a new pylacrosse reader thread. That thread stops for good when a serial read fails, for
example after a USB reset, while the device file stays present. A silent JeeLink
therefore causes a restart 15 to 16 minutes after its last frame with the default
timeout. jeelink2mqtt does not set `restart_on_stale` yet. Since cosalette 0.11.2 it
also covers streams and could reopen the serial port in place before the exit; its
adoption is planned.

!!! note "No sensors in range"

    Without a LaCrosse sensor in range, the receiver gets no frames, so jeelink2mqtt
    restarts about every 16 minutes with exit code 5. This also applies to `--dry-run`,
    whose fake adapter sends no frames.

**Adapter health check.** Every 30 s, cosalette also checks that the serial device file
(`JEELINK2MQTT_SERIAL_PORT`) exists. After 5 failed checks it restarts the adapter, at
most 3 times.

**Loop-stall watchdog.** The serial port opens and closes in the event loop. A close
waits for the reader thread, which is limited by the 2 s serial read timeout. If a USB
driver hangs in one of these calls, nothing else runs, including the freshness checks.
`compose.yml` sets `COSALETTE_LOOP_STALL_TIMEOUT` to `120` seconds, far above these
steps. After 120 s without a loop turn, jeelink2mqtt prints every thread's stack and
exits with code 6. Set `COSALETTE_LOOP_STALL_TIMEOUT` in the shell or `.env` to change
the value. Remove the line from `compose.yml` to disable the watchdog.

**Docker health status.** The image sets `COSALETTE_HEALTH_FILE` and probes it with
`cosalette-health` every 60 s, so `docker ps` shows `healthy` or `unhealthy`. The status
turns `unhealthy` when the receiver is `stale` or when the health file is older than
180 s. One receiver feeds every sensor, so the default `--fail-on stale` applies. The
60 s start period is roughly twice the 28.6 s startup of airthings2mqtt 0.3.0 on a Pi 4
at `--cpus 0.5`. jeelink2mqtt startup has not been measured on a Pi. An `unhealthy`
status restarts nothing: the exit codes below do. With a read-only root filesystem,
mount a tmpfs on `/tmp` for the health file.

| Exit code | Cause                                                                 |
| --------- | --------------------------------------------------------------------- |
| `1`       | Startup failure, or the event loop stalled while holding the GIL      |
| `3`       | Unexpected exception                                                  |
| `4`       | A framework task exhausted its restart budget                         |
| `5`       | The receiver stayed `stale` for 300 s                                 |
| `6`       | The event loop did not run for `COSALETTE_LOOP_STALL_TIMEOUT` seconds |

**Several receivers.** Run one jeelink2mqtt instance per JeeLink stick. When two
instances share a broker, give each its own `JEELINK2MQTT_MQTT__TOPIC_PREFIX` and
`JEELINK2MQTT_MQTT__INSTANCE_ID`. Setting the instance ID changes the Home Assistant
unique IDs once, so set it before the first start.

**Log redaction.** jeelink2mqtt does not set `App(redact=)`. Its logs and error payloads
carry the serial port, sensor IDs, sensor names and readings, but no secrets.

---

## Persistence

### Registry State

Sensor mappings are persisted to a JSON file store. Docker Compose defaults to:

```
/app/data/store.json
```

This file is updated after every mapping mutation (auto-adopt, manual
assign, reset).  On startup, the registry restores its state from this
file, so mappings survive restarts.

Set `JEELINK2MQTT_STORE_PATH` in `.env` to use a different path.

!!! danger "Docker: mount the data volume"

    Without a persistent volume, container restarts lose all mappings:

    ```yaml
    volumes:
      - jeelink-data:/app/data
    ```

### Backup

The state file is plain JSON — back it up with any file-copy tool:

```bash
cp /app/data/store.json /app/data/store.json.bak
```

---

## Structured Logging

jeelink2mqtt uses Python's standard `logging` module.  Control verbosity
via the `--log-level` CLI flag:

```bash
jeelink2mqtt --log-level DEBUG
```

| Level | What you see |
|-------|-------------|
| `ERROR` | Exceptions, serial failures |
| `WARNING` | Unparsable frames, unknown commands |
| `INFO` | Startup, shutdown, mapping events, periodic state |
| `DEBUG` | Every frame, every filter step, every publish |

!!! tip "Production recommendation"

    Use `INFO` in production.  Switch to `DEBUG` temporarily when
    diagnosing issues.

---

## Next Steps

- [Troubleshooting](troubleshooting.md) — common issues and fixes
- [Reference](reference.md) — complete settings and topic reference
