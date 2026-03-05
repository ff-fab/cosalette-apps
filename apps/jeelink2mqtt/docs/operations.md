# Operations

Deployment, monitoring, persistence, and logging configuration.

---

## Docker Deployment

### Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY packages/src/ packages/src/

FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/packages/src/ packages/src/

ENV PATH="/app/.venv/bin:$PATH"

# Persistence volume
VOLUME /app/data

ENTRYPOINT ["jeelink2mqtt"]
```

### docker-compose.yml

```yaml
services:
  jeelink2mqtt:
    build: .
    restart: unless-stopped
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
    volumes:
      - jeelink-data:/app/data
    environment:
      JEELINK2MQTT_SERIAL_PORT: /dev/ttyUSB0
      JEELINK2MQTT_MQTT__HOST: mosquitto
      JEELINK2MQTT_SENSORS: >-
        [
          {"name": "office", "temp_offset": -0.5},
          {"name": "outdoor", "staleness_timeout": 900}
        ]
      JEELINK2MQTT_STALENESS_TIMEOUT_SECONDS: "600"
      JEELINK2MQTT_MEDIAN_FILTER_WINDOW: "7"
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    restart: unless-stopped
    ports:
      - "1883:1883"
    volumes:
      - mosquitto-data:/mosquitto/data

volumes:
  jeelink-data:
  mosquitto-data:
```

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

## Persistence

### Registry State

Sensor mappings are persisted to a JSON file store:

```
data/jeelink2mqtt.json
```

This file is updated after every mapping mutation (auto-adopt, manual
assign, reset).  On startup, the registry restores its state from this
file, so mappings survive restarts.

!!! danger "Docker: mount the data volume"

    Without a persistent volume, container restarts lose all mappings:

    ```yaml
    volumes:
      - jeelink-data:/app/data
    ```

### Backup

The state file is plain JSON — back it up with any file-copy tool:

```bash
cp data/jeelink2mqtt.json data/jeelink2mqtt.json.bak
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
