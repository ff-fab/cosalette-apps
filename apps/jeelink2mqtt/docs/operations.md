# Operations

Deployment, monitoring, persistence, and logging configuration.

---

## Docker Deployment

The Docker files live in `apps/jeelink2mqtt/`:

- **Dockerfile** — multi-stage build using `uv` for fast dependency resolution
- **docker-compose.yml** — full stack with Mosquitto MQTT broker

### Build and Run

```bash
docker compose -f apps/jeelink2mqtt/docker-compose.yml up -d
```

To run in dry-run mode (no hardware or MQTT required):

```bash
docker compose -f apps/jeelink2mqtt/docker-compose.yml run --rm jeelink2mqtt --dry-run
```

### Configuration

Environment variables are set in `docker-compose.yml`.  Edit them
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
