# Getting Started

This guide walks you through setting up airthings2mqtt on a Raspberry Pi, connecting to
your Airthings Wave sensor over BLE, and verifying that data flows to your MQTT broker.

## Prerequisites

| Requirement         | Details                                             |
| ------------------- | --------------------------------------------------- |
| **Raspberry Pi**    | Any model with Bluetooth (Pi 3/4/5 or Zero 2 W)    |
| **Airthings Wave**  | Wave, Wave Plus, or Wave Mini (BLE-capable)         |
| **BlueZ**           | Linux Bluetooth stack (pre-installed on Raspbian)   |
| **MQTT broker**     | Mosquitto, EMQX, or any MQTT 3.1.1+ broker         |
| **Python**          | 3.14+ (Docker image includes this)                  |

### Finding Your Sensor MAC Address

airthings2mqtt needs the Bluetooth MAC address of your Airthings Wave sensor. Use
`bluetoothctl` to find it:

```bash
bluetoothctl scan on
```

Look for a device name starting with **"Airthings"**. The MAC address format is
`XX:XX:XX:XX:XX:XX`. Once found, press `Ctrl+C` to stop the scan.

!!! tip "Scan timeout"
    The sensor may take 30--60 seconds to appear. Make sure Bluetooth is enabled:
    `sudo systemctl status bluetooth` should show **active (running)**.

!!! note "BLE range"
    Bluetooth Low Energy range is typically 5--10 metres indoors. Place the Raspberry Pi
    within range of the sensor for reliable readings.

---

## Installation

=== "Docker (recommended)"

    Docker is the simplest way to run airthings2mqtt. Create a directory on your Pi,
    copy this `docker-compose.yml` into it, and you're ready to go:

    ```yaml title="docker-compose.yml"
    services:
      airthings2mqtt:
        image: ghcr.io/ff-fab/airthings2mqtt:latest
        restart: unless-stopped
        network_mode: host
        cap_add:
          - NET_ADMIN
          - SYS_ADMIN
        env_file: .env
        environment:
          AIRTHINGS2MQTT_MQTT__HOST: localhost
        volumes:
          - airthings2mqtt-data:/app/data
          - /var/run/dbus:/var/run/dbus:ro
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
      airthings2mqtt-data:
      mosquitto-data:
      mosquitto-log:
    ```

    Then download the Mosquitto config and create your env file:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/mosquitto.conf -o mosquitto.conf
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/.env.example -o .env
    # Edit .env with your sensor MAC address
    ```

    ```bash
    # Start airthings2mqtt + Mosquitto
    docker compose up -d
    ```

    The container uses `network_mode: host` to access the host D-Bus for Bluetooth.

    !!! tip "Download everything at once"
        Prefer `curl` over copy-paste? Grab all three files in one go:
        ```bash
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/docker-compose.yml -o docker-compose.yml
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/mosquitto.conf -o mosquitto.conf
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/airthings2mqtt/.env.example -o .env
        ```

    !!! note "Pin to a specific version"
        Replace `latest` with a release tag (e.g. `0.1.0`) in the `image:` line
        to pin the deployment and avoid surprises on restart.

    !!! warning "BlueZ and D-Bus access"
        BLE communication requires access to the host Bluetooth stack via D-Bus.
        The compose file mounts `/var/run/dbus` and adds `NET_ADMIN` / `SYS_ADMIN`
        capabilities for BlueZ access. `network_mode: host` avoids additional network
        configuration.

=== "Manual (pip/uv)"

    Install airthings2mqtt directly on your Pi:

    ```bash
    pip install airthings2mqtt
    # or with uv:
    uv pip install airthings2mqtt
    ```

    Create a `.env` file or set environment variables, then run:

    ```bash
    airthings2mqtt
    ```

    airthings2mqtt reads `.env` from the current directory by default.

---

## First Run Verification

Once airthings2mqtt is running, verify data is flowing by subscribing to the MQTT
topics.

### Check Status

```bash
mosquitto_sub -h localhost -t "airthings2mqtt/#" -v
```

You should see messages on these topics within the first polling cycle:

| Topic                                | What it means                         |
| ------------------------------------ | ------------------------------------- |
| `airthings2mqtt/status`              | Heartbeat --- the app is alive        |
| `airthings2mqtt/airthings/availability` | `"online"` --- sensor is ready     |
| `airthings2mqtt/airthings/state`     | First sensor reading (see below)      |

### Verify Sensor Data

The `airthings2mqtt/airthings/state` topic should contain a JSON payload with your
sensor readings:

```json
{
  "temperature": 21.5,
  "humidity": 45.0,
  "radon_24h_avg": 42,
  "radon_long_term_avg": 38
}
```

!!! info "Polling interval"
    The default polling interval is 1500 seconds (25 minutes). The first reading arrives
    shortly after startup; subsequent readings follow the configured interval. See
    [Configuration](configuration.md) to adjust.

!!! warning "No messages?"
    - Confirm the broker is reachable:
      `mosquitto_pub -h localhost -t test -m hello`
    - Check airthings2mqtt logs:
      `docker compose logs airthings2mqtt` or the terminal output
    - Verify Bluetooth:
      `bluetoothctl show` should list your controller
    - Check the sensor is in range:
      `bluetoothctl scan on` should show your Airthings device

---

## Next Steps

- [Configure](configuration.md) MQTT connection, polling intervals, and logging
- [MQTT Topics](mqtt-topics.md) --- full topic reference with payload schemas
