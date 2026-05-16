# Getting Started

This guide walks you through generating an SSH key, configuring wallpanel-control, and
sending your first MQTT commands.

## Prerequisites

| Requirement        | Details                                                         |
| ------------------ | --------------------------------------------------------------- |
| **Wall panel**     | Linux device with a GNOME desktop session (Intel NUC, SBC, mini-PC, ...) |
| **GNOME session**  | Required for screen on/off (D-Bus/Mutter); brightness uses sysfs and works without GNOME |
| **SSH access**     | Public-key login enabled on the wall panel                      |
| **WoL-capable NIC**| Required only for the `wake` system action                     |
| **MQTT broker**    | Mosquitto, EMQX, or any MQTT 3.1.1+ broker                     |
| **Python**         | 3.14+ (Docker image includes this)                             |

---

## SSH Key Setup

wallpanel-control uses public-key SSH authentication. Generate a dedicated key (no
passphrase so the container can connect unattended):

```bash
ssh-keygen -t ed25519 -C "wallpanel-control" -f ~/.ssh/wallpanel -N ""
```

Copy the public key to the wall panel:

```bash
ssh-copy-id -i ~/.ssh/wallpanel.pub jl4@wallpanel.lan
```

Verify the connection works before running the container:

```bash
ssh -i ~/.ssh/wallpanel jl4@wallpanel.lan "echo ok"
```

Capture the wall panel's host key in your local `known_hosts` (this step also seeds the
file that will be mounted into the container):

```bash
ssh-keyscan wallpanel.lan >> ~/.ssh/known_hosts
```

!!! warning "Container host-key verification"
    The container user (`appuser`) has no SSH history. The Compose file mounts your
    host `~/.ssh/known_hosts` read-only into the container, so the `ssh-keyscan` step
    above is required before starting the container. Without a `known_hosts` entry the
    container will refuse the connection.

!!! tip "Run as a dedicated user"
    Create a locked-down system user on the wall panel that only has permission to write
    to the sysfs backlight path and run `systemctl suspend` / `systemctl hibernate`.
    This limits the blast radius of a compromised key.

---

## Installation

=== "Docker (recommended)"

    Docker is the simplest deployment from a checkout of this monorepo. The checked-in
    Compose file includes a local `build:` block for development and an `image:` name for
    the release image:

    ```yaml title="compose.yml"
    services:
      wallpanel-control:
        build:
          context: ../..
          dockerfile: apps/wallpanel-control/Dockerfile
        image: ghcr.io/ff-fab/wallpanel-control:latest
        restart: unless-stopped
        env_file: .env
        environment:
          WALLPANEL_CONTROL_MQTT__HOST: mosquitto
          WALLPANEL_CONTROL_SSH_KEY_PATH: /run/secrets/wallpanel_ssh_key
          WALLPANEL_CONTROL_SSH_KNOWN_HOSTS: /run/secrets/wallpanel_known_hosts
        volumes:
          - wallpanel_control-data:/app/data
        secrets:
          - wallpanel_ssh_key
          - wallpanel_known_hosts
        depends_on:
          - mosquitto

      mosquitto:
        image: eclipse-mosquitto:2
        restart: unless-stopped
        ports:
          - '127.0.0.1:1883:1883'
        volumes:
          - ./mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
          - mosquitto-data:/mosquitto/data
          - mosquitto-log:/mosquitto/log

    volumes:
      wallpanel_control-data:
      mosquitto-data:
      mosquitto-log:

    secrets:
      wallpanel_ssh_key:
        file: ${HOST_WALLPANEL_SSH_KEY_PATH:-${HOME}/.ssh/wallpanel}
      wallpanel_known_hosts:
        file: ${HOST_WALLPANEL_KNOWN_HOSTS_PATH:-${HOME}/.ssh/known_hosts}
    ```

    From the app directory, create your env file:

    ```bash
    cd apps/wallpanel-control
    cp .env.example .env
    # Edit .env: set WALLPANEL_CONTROL_WOL_MAC to your panel's MAC address
    ```

    Start the stack:

    ```bash
    docker compose up -d
    ```

    !!! note "Pin to a specific version"
        Replace `latest` with a release tag (e.g. `0.2.0`) in the `image:` line to pin
        the deployment and avoid surprises on restart.

    !!! note "SSH key and known-hosts location"
        Export `HOST_WALLPANEL_SSH_KEY_PATH` and/or `HOST_WALLPANEL_KNOWN_HOSTS_PATH`
        in your shell to override the host-side paths for these Docker secrets. Do not
        set them in `.env` (they would be injected into the container as env vars).
        The container always reads from `/run/secrets/wallpanel_ssh_key` and
        `/run/secrets/wallpanel_known_hosts`.

=== "Manual (pip/uv)"

    Install wallpanel-control directly:

    ```bash
    pip install wallpanel-control
    # or with uv:
    uv pip install wallpanel-control
    ```

    Copy `.env.example` to `.env`, fill in your settings, then:

    ```bash
    wallpanel-control
    ```

---

## First MQTT Commands

With the stack running, open a second terminal and subscribe to all wallpanel topics:

```bash
mosquitto_sub -h localhost -t 'wallpanel-control/#' -v
```

### Turn the display on

```bash
mosquitto_pub -h localhost \
  -t wallpanel-control/display/set \
  -m '{"state": "on"}'
```

Example state response on `wallpanel-control/display/state`:

```json
{ "available": true, "state": "on", "brightness_percent": 60 }
```

### Set brightness to 40%

```bash
mosquitto_pub -h localhost \
  -t wallpanel-control/display/set \
  -m '{"brightness_percent": 40}'
```

### Turn display off

```bash
mosquitto_pub -h localhost \
  -t wallpanel-control/display/set \
  -m '{"state": "off"}'
```

### Send a system action

```bash
mosquitto_pub -h localhost \
  -t wallpanel-control/system/action/set \
  -m '{"action": "suspend"}'
```

Expected acknowledgement on `wallpanel-control/system/action/state`:

```json
{ "accepted": true, "action": "suspend" }
```

!!! warning "WoL requires same-subnet broadcast"
    The `wake` action sends a magic packet to `WALLPANEL_CONTROL_WOL_BROADCAST`
    (default `255.255.255.255`). If the wall panel is on a different subnet, set
    this to the directed broadcast address for that subnet.
