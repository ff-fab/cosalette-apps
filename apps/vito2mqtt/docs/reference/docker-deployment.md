# Docker Deployment Guide

Deploy vito2mqtt in Docker for isolation, reproducibility, and easier management across different Linux hosts.

## Prerequisites

- **Docker**: 20.10+ ([install](https://docs.docker.com/engine/install/))
- **Docker Compose**: 2.0+ (included with Docker Desktop; on Linux, `pip install docker-compose`)
- **Serial device**: USB-to-serial adapter (CH340, FTDI, etc.) accessible via `/dev/ttyUSB0`
- **MQTT broker endpoint**: Either Docker-hosted (this guide) or external

## Quick Start

### 1. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/fabiankoerner/vito2mqtt.git
cd vito2mqtt

# Create configuration from template
cp .env.example .env

# Edit .env for your environment (optional, defaults work with docker-compose)
nano .env  # or your editor
```

### 2. Verify Serial Device

Ensure your USB serial adapter is connected and recognized:

```bash
# List USB devices
lsusb

# Find the device path:
# /dev/ttyUSB0 (CH340, Prolific)
# /dev/ttyACM0 (CH340G with Arduino driver, CP2102)
ls -la /dev/tty*

# Try connecting to identify baud rate and protocol
minicom -D /dev/ttyUSB0  # Use Ctrl+A, Q to exit
```

If using a different device path (e.g., `/dev/ttyUSB1`), update both:
- `docker-compose.yml`: `devices:` section
- `.env`: `VITO2MQTT_SERIAL_PORT`

### 3. Start Services

```bash
# Build vito2mqtt image and start both services (Mosquitto + vito2mqtt)
docker-compose up

# Detached mode (runs in background)
docker-compose up -d

# View logs
docker-compose logs -f         # All services
docker-compose logs -f vito2mqtt  # Just the app
```

The app will automatically attempt to connect to the heating device on startup. Check logs for any connection errors.

### 4. Verify MQTT Connectivity

From another terminal:

```bash
# Subscribe to all vito2mqtt topics and monitor messages
docker exec -it vito2mqtt-mosquitto mosquitto_sub -h localhost -t 'vito2mqtt/#' -v

# Or use the MQTT CLI tool (if installed)
mqtt subscribe --uri mqtt://localhost vito2mqtt/#

# Or from another host on the network:
mqtt subscribe --uri mqtt://192.168.1.10 vito2mqtt/#
```

You should see telemetry messages appear at the intervals specified in `VITO2MQTT_POLLING_*`.

## Configuration

### Environment Variables

See [`.env.example`](../../.env.example) for all options. Key variables:

#### Serial Connection

```env
VITO2MQTT_SERIAL_PORT=/dev/ttyUSB0
VITO2MQTT_SERIAL_BAUD_RATE=4800
```

#### MQTT Broker

```env
# Docker-hosted (docker-compose)
VITO2MQTT_MQTT__HOST=mosquitto
VITO2MQTT_MQTT__PORT=1883

# External broker
VITO2MQTT_MQTT__HOST=192.168.1.100
VITO2MQTT_MQTT__PORT=1883
VITO2MQTT_MQTT__USERNAME=api
VITO2MQTT_MQTT__PASSWORD=secret123
```

#### Device Identity

```env
VITO2MQTT_DEVICE_ID=vitodens200w
VITO2MQTT_SIGNAL_LANGUAGE=en
```

#### Polling (seconds)

```env
VITO2MQTT_POLLING_OUTDOOR=300
VITO2MQTT_POLLING_HOT_WATER=300
VITO2MQTT_POLLING_HEATING_RADIATOR=300
```

### Applying Configuration Changes

```bash
# Stop services
docker-compose down

# Modify .env
nano .env

# Restart
docker-compose up -d
```

## Serial Device Access

### Default: `--device` Flag (Recommended for Development)

The `docker-compose.yml` uses:

```yaml
devices:
  - /dev/ttyUSB0:/dev/ttyUSB0
```

This grants container access to `/dev/ttyUSB0` directly. Works for single-machine setups.

**If using a different device:**

```yaml
devices:
  - /dev/ttyUSB1:/dev/ttyUSB1  # For /dev/ttyUSB1
  - /dev/ttyACM0:/dev/ttyACM0  # For Arduino-style
```

### Production: udev Rules (Recommended for Stability)

For consistent device naming across reboots, define udev rules on the host:

Create `/etc/udev/rules.d/99-viessmann.rules`:

```udev
# Viessmann Optolink adapter (adjust VendorID:ProductID for your hardware)
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", \
  SYMLINK+="viessmann", MODE="0666"
```

Reload rules and reconnect device:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
ls -la /dev/viessmann
```

Update configuration:

```env
VITO2MQTT_SERIAL_PORT=/dev/viessmann
```

### Troubleshooting Device Access

If container reports "device not found":

```bash
# Check if device exists on host
ls -la /dev/ttyUSB0

# Verify container can access it
docker exec vito2mqtt ls -la /dev/ttyUSB0

# Check permissions
sudo chmod 666 /dev/ttyUSB0

# Or add container user to dialout group (requires container rebuild)
```

## Data Persistence

vito2mqtt stores device state (e.g., legionella treatment timestamps) in a JSON
file. In Docker, this is persisted via a named volume:

```yaml
volumes:
  - vito2mqtt-data:/app/data
environment:
  VITO2MQTT_STORE_PATH: /app/data/store.json
```

The `docker-compose.yml` configures this automatically. The state file survives
container restarts and image upgrades.

### Inspecting or Resetting State

```bash
# View the current store contents
docker exec vito2mqtt-app cat /app/data/store.json

# Reset state (removes all stored data)
docker compose down
docker volume rm vito2mqtt_vito2mqtt-data
docker compose up -d
```

### Mosquitto Data Volume

Messages and subscriptions are stored in the named volume `mosquitto-data`.
This persists across container restarts and removals until explicitly deleted.

!!! note "Volume name prefix"
    Docker Compose prefixes volume names with the project name (directory name by
    default). If you cloned into `vito2mqtt/`, the actual volume names are
    `vito2mqtt_mosquitto-data`, `vito2mqtt_vito2mqtt-data`, etc.

```bash
# Inspect volume (prefix matches your project directory name)
docker volume inspect vito2mqtt_mosquitto-data

# List all volumes
docker volume ls

# Delete volume (warning: removes persisted data)
docker volume rm vito2mqtt_mosquitto-data
```

## Monitoring and Debugging

### View Logs

```bash
# Real-time logs for all services
docker-compose logs -f

# Just vito2mqtt (colorized, last 100 lines)
docker-compose logs -f vito2mqtt --tail 100

# With timestamps
docker-compose logs -f vito2mqtt --timestamps
```

### Check Service Status

```bash
# List running containers
docker-compose ps

# Show container resource usage (CPU, memory)
docker stats vito2mqtt vito2mqtt-mosquitto
```

### Connect to Container Shell

```bash
# Run interactive bash in vito2mqtt container
docker exec -it vito2mqtt bash

# Run a command directly
docker exec vito2mqtt vito2mqtt --version
```

### MQTT Debugging

```bash
# Listen to all MQTT messages
docker exec vito2mqtt-mosquitto mosquitto_sub -t '#' -v

# Publish test message
docker exec vito2mqtt-mosquitto mosquitto_pub -t 'test/hello' -m 'world'

# Check broker logs
docker-compose logs mosquitto
```

## Resource Limits

`docker-compose.yml` defines resource limits to prevent the app from consuming excessive CPU/memory:

```yaml
deploy:
  resources:
    limits:
      cpus: '1'
      memory: 512M
    reservations:
      memory: 256M
```

**Adjust for your hardware:**

- **Raspberry Pi 4B**: Set `cpus` to 2–3, `memory` to 256–512M
- **x86 NAS/server**: Can increase limits if supporting other workloads
- **Low-power systems**: Reduce to `0.5` CPU, 128M memory

Apply changes:

```bash
nano docker-compose.yml
docker-compose up -d
```

## Health Checks

The `Dockerfile` includes a basic health check (executes every 30s):

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1
```

View health status:

```bash
docker inspect --format='{{.State.Health.Status}}' vito2mqtt
docker ps  # Shows "healthy" or "unhealthy" in the STATUS column
```

**Future:** Expand health check to verify MQTT connectivity and device communication.

## Production Setup

### Reverse Proxy (Nginx/Caddy)

If exposing MQTT to the network (not recommended without auth):

```nginx
# Nginx (TCP reverse proxy, not HTTP)
upstream mqtt {
  server 192.168.1.100:1883;
}

server {
  listen 1883;
  proxy_pass mqtt;
}
```

Better: Keep MQTT internal and use firewall rules.

### Authentication

Enable Mosquitto authentication by creating a config file:

Create `mosquitto.conf`:

```conf
allow_anonymous false
password_file /mosquitto/config/passwd
listener 1883 0.0.0.0
```

Create password file:

```bash
docker run --rm -it eclipse-mosquitto:2 mosquitto_passwd -c /tmp/passwd user1
# Enter password when prompted

# Copy to host mount
docker cp <container>:/tmp/passwd ./mosquitto/passwd
```

Update `docker-compose.yml`:

```yaml
mosquitto:
  volumes:
    - ./mosquitto/passwd:/mosquitto/config/passwd
    - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
    - mosquitto-data:/mosquitto/data
```

### TLS/SSL

For secure MQTT over TLS:

1. Obtain certificates (Let's Encrypt, self-signed, etc.)
2. Configure Mosquitto with TLS listener
3. Update vito2mqtt config: `VITO2MQTT_MQTT__TLS=true`

See [Mosquitto TLS documentation](https://mosquitto.org/documentation/authentication-methods/).

## Updating the Application

### Pull Latest Changes

```bash
git pull origin main
```

### Rebuild Image

```bash
docker-compose build --no-cache
docker-compose up -d
```

If the image build fails, check:

```bash
docker-compose build --no-cache --progress=plain
```

### Database/Migration

vito2mqtt does not use a database. Configuration is stateless MQTT pub/sub.

## Stopping and Cleanup

```bash
# Stop services (containers persist)
docker-compose stop

# Stop and remove containers
docker-compose down

# Stop, remove containers, and delete volumes (⚠️ deletes Mosquitto data)
docker-compose down -v

# Remove unused images/volumes (cleanup)
docker system prune -a --volumes
```

## Docker Network Modes

The default `docker-compose.yml` uses bridge networking (`networks.vito_network`).

**Service-to-service communication** uses internal DNS:
- `mosquitto` (vito2mqtt connects to `mqtt://mosquitto:1883`)
- `vito2mqtt` (the app, not externally accessible by name)

**Port exposure:** Only `mosquitto:1883` is published to the host.

**Alternative: Host Networking** (not recommended):

```yaml
vito2mqtt:
  network_mode: host
```

Trade-offs:
- ✅ Direct hardware access
- ✅ Lower latency
- ❌ No service isolation
- ❌ Port conflicts possible

## Troubleshooting

### "Cannot connect to serial device"

```bash
# Check device exists on host
ls /dev/ttyUSB*

# Verify docker-compose.yml devices section matches
# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### "Cannot connect to MQTT broker"

```bash
# Verify Mosquitto is running
docker-compose ps
docker logs vito2mqtt-mosquitto

# Check network connectivity
docker exec vito2mqtt ping mosquitto

# Verify environment variables were loaded
docker exec vito2mqtt env | grep VITO2MQTT
```

### High CPU Usage

- Check polling intervals (`VITO2MQTT_POLLING_*`)
- Verify serial connection isn't looping with retries
- Check MQTT broker performance (`docker stats`)

### Logs Fill Up

Configure log rotation in `docker-compose.yml`:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"  # Keep 3 files, 10 MB each
```

## Advanced Configuration

### Multiple Devices

To run multiple vito2mqtt instances (different adaptation or device IDs):

```yaml
vito2mqtt-1:
  build: .
  env_file: .env.device1
  devices:
    - /dev/ttyUSB0:/dev/ttyUSB0
  depends_on:
    - mosquitto

vito2mqtt-2:
  build: .
  env_file: .env.device2
  devices:
    - /dev/ttyUSB1:/dev/ttyUSB1
  depends_on:
    - mosquitto
```

Create separate `.env.device1` and `.env.device2` files with different device IDs and polling intervals.

### External MQTT Broker

To connect to a remote MQTT broker instead of docker-hosted Mosquitto:

```yaml
services:
  vito2mqtt:
    # Remove depends_on: mosquitto line
    env_file: .env
```

Update `.env`:

```env
VITO2MQTT_MQTT__HOST=mqtt.example.com
VITO2MQTT_MQTT__PORT=1883
VITO2MQTT_MQTT__USERNAME=api
VITO2MQTT_MQTT__PASSWORD=secret
```

Remove or comment out the `mosquitto` service from `docker-compose.yml`.

### Build Arguments

Customize image builds with build arguments (e.g., Python version):

```yaml
services:
  vito2mqtt:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        PYTHON_VERSION: "3.14"  # Build argument (not yet implemented)
```

## See Also

- [Configuration Reference](./configuration.md)
- [Signal Reference](./signals.md)
- [Architecture Decisions](../adr/index.md)
