# Getting Started

This guide walks you through installing gas2mqtt, connecting the QMC5883L sensor, and
verifying that data flows to your MQTT broker.

## Prerequisites

| Requirement      | Details                                        |
| ---------------- | ---------------------------------------------- |
| **Raspberry Pi** | Any model with I2C (Pi 3/4/5 or Zero 2 W)      |
| **QMC5883L**     | 3-axis magnetometer breakout board (I2C, 0x0D) |
| **MQTT broker**  | Mosquitto, EMQX, or any MQTT 3.1.1+ broker     |
| **Python**       | 3.14+ (Docker image includes this)             |

### Wiring

Connect the QMC5883L to the Raspberry Pi I2C pins:

| QMC5883L | Raspberry Pi   |
| -------- | -------------- |
| VCC      | 3.3V (pin 1)   |
| GND      | GND (pin 6)    |
| SDA      | GPIO 2 (pin 3) |
| SCL      | GPIO 3 (pin 5) |

<figure markdown>
  ![Raspberry Pi to QMC5883L wiring diagram](assets/images/rpi-qmc5883l-wiring.svg){ width="680" }
  <figcaption>Four-wire I2C connection — no external pull-up resistors needed (the breakout board includes them).</figcaption>
</figure>

!!! tip "Enable I2C" Run `sudo raspi-config` → **Interface Options** → **I2C** →
**Enable**, then reboot. Verify with `i2cdetect -y 1` — you should see `0d` in the
output.

---

## Installation

=== "Docker (recommended)"

    Docker is the simplest way to run gas2mqtt. Create a directory on your Pi,
    copy this `docker-compose.yml` into it, and you're ready to go:

    ```yaml title="docker-compose.yml"
    services:
      gas2mqtt:
        image: ghcr.io/ff-fab/gas2mqtt:latest
        restart: unless-stopped
        devices:
          - /dev/i2c-1:/dev/i2c-1
        group_add:
          - i2c
        env_file: .env
        environment:
          # Override MQTT host to use Docker Compose service name
          GAS2MQTT_MQTT__HOST: mosquitto
        volumes:
          - gas2mqtt-data:/app/data
        depends_on:
          - mosquitto

      mosquitto:
        image: eclipse-mosquitto:2
        restart: unless-stopped
        ports:
          - '1883:1883'
        volumes:
          - ./mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
          - mosquitto-data:/mosquitto/data
          - mosquitto-log:/mosquitto/log

    volumes:
      gas2mqtt-data:
      mosquitto-data:
      mosquitto-log:
    ```

    Then download the Mosquitto config and create your env file:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/gas2mqtt/mosquitto.conf -o mosquitto.conf
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/gas2mqtt/.env.example -o .env
    # Edit .env with your MQTT broker and sensor settings
    ```

    ```bash
    # Start gas2mqtt + Mosquitto
    docker compose up -d
    ```

    The container needs I2C host access (`/dev/i2c-1`), which the Compose file
    maps automatically.

    !!! tip "Download everything at once"
        Prefer `curl` over copy-paste? Grab all three files in one go:
        ```bash
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/gas2mqtt/docker-compose.yml -o docker-compose.yml
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/gas2mqtt/mosquitto.conf -o mosquitto.conf
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/gas2mqtt/.env.example -o .env
        ```

    !!! note "Pin to a specific version"
        Replace `latest` with a release tag (e.g. `0.2.0`) in the `image:` line
        to pin the deployment and avoid surprises on restart.

    !!! note "Custom I2C bus"
        If your sensor is on a different bus (e.g., `/dev/i2c-0`), update both the
        device mapping in `docker-compose.yml` and `GAS2MQTT_I2C_BUS` in `.env`.

=== "Manual (pip/uv)"

    Install gas2mqtt directly on your Pi:

    ```bash
    pip install gas2mqtt
    # or with uv:
    uv pip install gas2mqtt
    ```

    Create a `.env` file or set environment variables, then run:

    ```bash
    gas2mqtt
    ```

    gas2mqtt reads `.env` from the current directory by default.

---

## First Run Verification

Once gas2mqtt is running, verify data is flowing by subscribing to the MQTT topics.

### Check Status

```bash
mosquitto_sub -h localhost -t "gas2mqtt/#" -v
```

You should see messages on these topics within the first minute:

| Topic                               | What it means                     |
| ----------------------------------- | --------------------------------- |
| `gas2mqtt/status`                   | Heartbeat — the app is alive      |
| `gas2mqtt/gas_counter/availability` | `"online"` — gas counter is ready |
| `gas2mqtt/temperature/availability` | `"online"` — temperature is ready |
| `gas2mqtt/gas_counter/state`        | Initial state (counter = 0)       |
| `gas2mqtt/temperature/state`        | First temperature reading         |

### Verify a Gas Tick

Move a magnet near the sensor. You should see `gas2mqtt/gas_counter/state` update with
an incremented counter and the trigger changing between `"OPEN"` and `"CLOSED"`.

!!! warning "No messages?" - Confirm the broker is reachable:
`mosquitto_pub -h localhost -t test -m hello` - Check gas2mqtt logs:
`docker compose logs gas2mqtt` or the terminal output - Verify I2C: `i2cdetect -y 1`
should show `0d`

---

## Next Steps

- [Configure](configuration.md) thresholds, intervals, and consumption tracking
- [MQTT Topics](mqtt-topics.md) — full topic reference with payload schemas
- [Architecture](architecture.md) — understand how gas2mqtt works internally
