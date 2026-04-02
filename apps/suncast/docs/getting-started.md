# Getting Started

This guide walks you through installing suncast and verifying that shadow
visualizations flow to your MQTT broker.

## Prerequisites

| Requirement     | Details                                           |
| --------------- | ------------------------------------------------- |
| **MQTT broker** | Mosquitto or any MQTT 3.1.1+ compatible broker    |
| **Python**      | 3.14+ (Docker image includes this)                |
| **Hardware**    | None — suncast is a pure computation service       |

---

## Installation

=== "Docker (recommended)"

    Docker is the simplest way to run suncast. The Compose stack includes suncast,
    an nginx sidecar for serving SVGs over HTTP, and Mosquitto.

    ```yaml title="docker-compose.yml"
    services:
      suncast:
        image: ghcr.io/ff-fab/suncast:latest
        restart: unless-stopped
        env_file: .env
        environment:
          SUNCAST_MQTT__HOST: mosquitto
        volumes:
          - shadow-output:/output
          - suncast-data:/app/data
          - ./geometry.yaml:/app/geometry.yaml:ro
        depends_on:
          - mosquitto

      shadow-web:
        image: nginx:alpine
        restart: unless-stopped
        ports:
          - '8080:80'
        volumes:
          - shadow-output:/usr/share/nginx/html:ro

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
      shadow-output:
      suncast-data:
      mosquitto-data:
      mosquitto-log:
    ```

    Download the supporting files and create your env:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/suncast/mosquitto.conf -o mosquitto.conf
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/suncast/.env.example -o .env
    curl -fsSL https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/suncast/geometry.example.yaml -o geometry.yaml
    ```

    Edit `.env` with your location (latitude, longitude, timezone), then start:

    ```bash
    docker compose up -d
    ```

    The nginx sidecar serves the rendered SVG at `http://<host>:8080/shadow.svg`.

    !!! tip "Download everything at once"
        Grab all files in one go:
        ```bash
        for f in docker-compose.yml mosquitto.conf .env.example geometry.example.yaml; do
          curl -fsSL "https://raw.githubusercontent.com/ff-fab/cosalette-apps/main/apps/suncast/$f" -o "$f"
        done
        mv .env.example .env
        mv geometry.example.yaml geometry.yaml
        ```

    !!! note "Pin to a specific version"
        Replace `latest` with a release tag (e.g. `0.1.0`) in the `image:` line
        to pin the deployment.

    See the full [docker-compose.yml reference](https://github.com/ff-fab/cosalette-apps/blob/main/apps/suncast/docker-compose.yml)
    for health checks and volume details.

=== "Manual (pip/uv)"

    Install suncast directly:

    ```bash
    pip install suncast
    # or with uv:
    uv pip install suncast
    ```

    Create a `.env` file and geometry configuration:

    ```bash
    cp .env.example .env
    cp geometry.example.yaml geometry.yaml
    # Edit .env with your location
    ```

    Run:

    ```bash
    suncast
    # or:
    uv run suncast
    ```

    suncast reads `.env` from the current directory by default.

---

## First Run Verification

Once suncast is running, verify data is flowing by subscribing to the MQTT topics.

```bash
mosquitto_sub -h localhost -t "suncast/#" -v
```

You should see messages on these topics within the first poll cycle
(default: 6 minutes):

| Topic                           | What it means                    |
| ------------------------------- | -------------------------------- |
| `suncast/status`                | Heartbeat — the app is alive     |
| `suncast/shadow/availability`   | `"online"` — shadow device ready |
| `suncast/shadow/svg`            | SVG visualization content        |

!!! tip "SVG on every cycle"
    The SVG is published on every poll cycle, not just on change. This ensures
    dashboards always receive the latest visualization even after reconnecting.

!!! warning "No messages?"
    - Confirm the broker is reachable:
      `mosquitto_pub -h localhost -t test -m hello`
    - Check suncast logs:
      `docker compose logs suncast` or the terminal output
    - Verify your `.env` contains valid `SUNCAST_LATITUDE`,
      `SUNCAST_LONGITUDE`, and `SUNCAST_TIMEZONE`

---

## Acknowledgements

The sun position and shadow visualization concept was originally created by
[pmpkk (Patrick)](https://community.openhab.org/t/show-current-sun-position-and-shadow-of-house-generate-svg/34764)
on the openHAB community forum. suncast reimplements the idea as a standalone
MQTT service built on the cosalette framework.

---

## Next Steps

- [Configuration](configuration.md) — settings reference for location, rendering,
  and output
- [MQTT Topics](mqtt-topics.md) — full topic reference with payload schemas
