# Getting Started

This guide walks you through setting up caldates2mqtt, connecting to your CalDAV
calendars, and verifying that event data flows to your MQTT broker.

## Prerequisites

| Requirement      | Details                                              |
| ---------------- | ---------------------------------------------------- |
| **CalDAV server**| Nextcloud, Baikal, Radicale, or any CalDAV-compliant server |
| **MQTT broker**  | Mosquitto, EMQX, or any MQTT 3.1.1+ broker          |
| **Python**       | 3.14+ (Docker image includes this)                   |

!!! note "No special hardware required"
    Unlike other cosalette apps that need BLE adapters or GPIO access, caldates2mqtt only
    needs network access to the CalDAV server and MQTT broker.

---

## Installation

=== "Docker (recommended)"

    Docker is the simplest way to run caldates2mqtt. Create a directory, copy this
    `docker-compose.yml` into it, and you're ready to go:

    ```yaml title="docker-compose.yml"
    services:
      caldates2mqtt:
        image: ghcr.io/ff-fab/caldates2mqtt:latest
        restart: unless-stopped
        env_file: .env
        environment:
          CALDATES2MQTT_MQTT__HOST: mosquitto
        volumes:
          - caldates2mqtt-data:/app/data
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
      caldates2mqtt-data:
      mosquitto-data:
      mosquitto-log:
    ```

    Then download the Mosquitto config and create your env file:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/caldates2mqtt/mosquitto.conf -o mosquitto.conf
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/caldates2mqtt/.env.example -o .env
    # Edit .env with your CalDAV credentials
    ```

    ```bash
    # Start caldates2mqtt + Mosquitto
    docker compose up -d
    ```

    !!! tip "Download everything at once"
        ```bash
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/caldates2mqtt/docker-compose.yml -o docker-compose.yml
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/caldates2mqtt/mosquitto.conf -o mosquitto.conf
        curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/caldates2mqtt/.env.example -o .env
        ```

    !!! note "Pin to a specific version"
        Replace `latest` with a release tag (e.g. `0.1.0`) in the `image:` line
        to pin the deployment and avoid surprises on restart.

=== "Manual (pip/uv)"

    Install caldates2mqtt directly:

    ```bash
    pip install caldates2mqtt
    # or with uv:
    uv pip install caldates2mqtt
    ```

    Create a `.env` file or set environment variables, then run:

    ```bash
    caldates2mqtt
    ```

    caldates2mqtt reads `.env` from the current directory by default.

---

## Configuring Calendars

caldates2mqtt requires at least one calendar configuration. Calendars are passed as a
JSON list in the `CALDATES2MQTT_CALENDARS` environment variable.

### Single Calendar (Nextcloud Example)

```dotenv title=".env"
CALDATES2MQTT_MQTT__HOST=localhost
CALDATES2MQTT_CALENDARS='[{"key":"garbage","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"abfall","username":"user","password":"secret"}]'
```

### Multiple Calendars

```dotenv title=".env"
CALDATES2MQTT_MQTT__HOST=localhost
CALDATES2MQTT_CALENDARS='[{"key":"garbage","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"abfall","username":"user","password":"secret","entries":5,"days":14},{"key":"birthday","url":"https://cloud.example.com/remote.php/dav/calendars/user/","calendar_name":"birthdays","username":"user","password":"secret","entries":10,"days":30}]'
```

Each calendar becomes its own MQTT device. The `key` field is used as the device name in
MQTT topics (e.g. `caldates2mqtt/garbage/state`).

!!! tip "Finding your Nextcloud CalDAV URL"
    In Nextcloud, open **Calendar** settings and click the `...` menu next to your
    calendar. Select **Copy private link**. The CalDAV URL is typically:

    ```
    https://your-nextcloud.example.com/remote.php/dav/calendars/username/
    ```

    The `calendar_name` is the last path segment of the specific calendar URL
    (e.g. `personal`, `birthdays`, `abfall_shared_by_fab`).

---

## First Run Verification

Once caldates2mqtt is running, verify data is flowing by subscribing to the MQTT topics.

### Check Status

```bash
mosquitto_sub -h localhost -t "caldates2mqtt/#" -v
```

You should see messages on these topics within the first polling cycle:

| Topic                                 | What it means                          |
| ------------------------------------- | -------------------------------------- |
| `caldates2mqtt/status`                | Heartbeat --- the app is alive         |
| `caldates2mqtt/garbage/availability`  | `"online"` --- calendar device is ready|
| `caldates2mqtt/garbage/state`         | First calendar reading (see below)     |

### Verify Calendar Data

The `caldates2mqtt/garbage/state` topic should contain a JSON payload with upcoming
events:

```json
{
  "events": [
    {"title": "Gelber Sack", "date": "2026-04-01"},
    {"title": "Restmuell", "date": "2026-04-08"}
  ]
}
```

!!! info "Polling interval"
    The default polling interval is 7200 seconds (2 hours). The first reading arrives
    shortly after startup; subsequent readings follow the configured interval. See
    [Configuration](configuration.md) to adjust.

!!! warning "No messages?"
    - Confirm the broker is reachable:
      `mosquitto_pub -h localhost -t test -m hello`
    - Check caldates2mqtt logs:
      `docker compose logs caldates2mqtt` or the terminal output
    - Verify CalDAV connectivity --- can you reach the CalDAV URL from the machine
      running caldates2mqtt?
    - Check credentials --- incorrect username/password will produce error messages
      on `caldates2mqtt/error`

---

## Triggering a Re-Read

You can trigger an immediate re-read of any calendar by publishing a command to its
`/set` topic:

```bash
# Re-read with default parameters
mosquitto_pub -h localhost -t "caldates2mqtt/garbage/set" -m ""

# Re-read with overrides: 10 entries, 30-day lookahead
mosquitto_pub -h localhost -t "caldates2mqtt/garbage/set" -m '{"entries":10,"days":30}'
```

---

## Next Steps

- [Configure](configuration.md) MQTT connection, polling intervals, and calendar settings
- [MQTT Topics](mqtt-topics.md) --- full topic reference with payload schemas
