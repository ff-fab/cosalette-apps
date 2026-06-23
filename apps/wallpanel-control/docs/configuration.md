# Configuration

wallpanel-control uses
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for
configuration, with four priority levels for setting values:

1. **CLI flags** -- highest priority
2. **Environment variables** -- `WALLPANEL_CONTROL_` prefix
3. **`.env` file** -- loaded from the working directory
4. **Defaults** -- built-in sensible values

Higher-priority sources override lower ones. For most deployments, a `.env` file is all
you need.

---

## Settings Reference

### MQTT

| Setting  | Environment Variable                        | Default      | Description                        |
| -------- | ------------------------------------------- | ------------ | ---------------------------------- |
| Host     | `WALLPANEL_CONTROL_MQTT__HOST`              | `localhost`  | MQTT broker hostname               |
| Port     | `WALLPANEL_CONTROL_MQTT__PORT`              | `1883`       | MQTT broker port                   |
| Username | `WALLPANEL_CONTROL_MQTT__USERNAME`          | --           | Broker username                    |
| Password | `WALLPANEL_CONTROL_MQTT__PASSWORD`          | --           | Broker password                    |
| Topic prefix | `WALLPANEL_CONTROL_MQTT__TOPIC_PREFIX`  | `wallpanel-control` | Root prefix for all MQTT topics |
| TLS          | `WALLPANEL_CONTROL_MQTT__TLS`           | `false`             | Enable TLS for broker connection |
| TLS CA file  | `WALLPANEL_CONTROL_MQTT__TLS_CA_FILE`   | --                  | CA bundle for broker certificate verification |
| TLS cert     | `WALLPANEL_CONTROL_MQTT__TLS_CERT_FILE` | --                  | Client certificate for mutual TLS |
| TLS key      | `WALLPANEL_CONTROL_MQTT__TLS_KEY_FILE`  | --                  | Client private key for mutual TLS |

!!! tip "Secure broker connections"
    Set `WALLPANEL_CONTROL_MQTT__TLS=true` when connecting to a broker outside
    localhost. Provide `TLS_CA_FILE` to verify the broker's certificate.
    For mutual TLS (client authentication), also set `TLS_CERT_FILE` and
    `TLS_KEY_FILE`. See `.env.example` for commented examples.

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate nesting levels:

    `WALLPANEL_CONTROL_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### Logging

| Setting | Environment Variable                        | Default | Description                    |
| ------- | ------------------------------------------- | ------- | ------------------------------ |
| Level   | `WALLPANEL_CONTROL_LOGGING__LEVEL`          | `INFO`  | Root log level                 |
| Format  | `WALLPANEL_CONTROL_LOGGING__FORMAT`         | `json`  | `json` or `text` output format |

!!! tip "Choosing a log format"
    Use `json` (the default) for Docker and container environments. Use `text` for
    local development where human-readable output is more convenient.

### SSH

| Setting      | Environment Variable                        | Default                              | Description                          |
| ------------ | ------------------------------------------- | ------------------------------------ | ------------------------------------ |
| Host         | `WALLPANEL_CONTROL_SSH_HOST`                | `wallpanel.lan`                      | Hostname or IP of the wall panel     |
| User         | `WALLPANEL_CONTROL_SSH_USER`                | `jl4`                                | SSH login username                   |
| Key path     | `WALLPANEL_CONTROL_SSH_KEY_PATH`            | `~/.ssh/wallpanel`                   | Path to SSH private key file         |
| Known hosts  | `WALLPANEL_CONTROL_SSH_KNOWN_HOSTS`         | `~/.ssh/known_hosts`                 | Path to SSH known_hosts file         |
| Port         | `WALLPANEL_CONTROL_SSH_PORT`                | `22`                                 | SSH port number                      |
| Timeout      | `WALLPANEL_CONTROL_SSH_TIMEOUT`             | `5.0`                                | Connection timeout in seconds        |
| Backlight path | `WALLPANEL_CONTROL_BACKLIGHT_PATH`        | `/sys/class/backlight/intel_backlight/brightness` | Sysfs brightness file |

!!! note "Docker key and known-hosts paths"
    In the Docker Compose setup the SSH key is mounted read-only at
    `/run/secrets/wallpanel_ssh_key` and the known_hosts file at
    `/run/secrets/wallpanel_known_hosts`. The Compose `environment:` block
    overrides `WALLPANEL_CONTROL_SSH_KEY_PATH` and
    `WALLPANEL_CONTROL_SSH_KNOWN_HOSTS` to these paths automatically.

    `HOST_WALLPANEL_SSH_KEY_PATH` and `HOST_WALLPANEL_KNOWN_HOSTS_PATH` control
    the **host-side** source paths for these secrets. They are Compose
    interpolation variables only — **do not put them in `.env`**. Because `.env`
    is also the service `env_file:`, any variable there is injected into the
    container environment. Export them in your shell instead:

    ```bash
    export HOST_WALLPANEL_SSH_KEY_PATH=/home/you/.ssh/wallpanel
    export HOST_WALLPANEL_KNOWN_HOSTS_PATH=/home/you/.ssh/known_hosts
    ```

!!! warning "Backlight path validation"
    `WALLPANEL_CONTROL_BACKLIGHT_PATH` must be an absolute path starting with
    `/sys/class/backlight/` and ending with `/brightness`. The app refuses to start
    with an invalid path as a security guard against writing to arbitrary files.

### Wake-on-LAN

| Setting       | Environment Variable                    | Default           | Description                              |
| ------------- | --------------------------------------- | ----------------- | ---------------------------------------- |
| MAC address   | `WALLPANEL_CONTROL_WOL_MAC`             | **required**      | Wall panel MAC address for WoL           |
| Broadcast     | `WALLPANEL_CONTROL_WOL_BROADCAST`       | `255.255.255.255` | UDP broadcast address for magic packets  |

!!! warning "WoL MAC is required"
    The app will not start without `WALLPANEL_CONTROL_WOL_MAC`. Use the format
    `AA:BB:CC:DD:EE:FF`.

---

## `.env` File

Copy `.env.example` to `.env` and edit it. A minimal deployment needs only the MAC
address; all other settings have sensible defaults:

```bash
cp .env.example .env
# Edit WALLPANEL_CONTROL_WOL_MAC with the wall panel's MAC address
```

See `.env.example` for the full list of available variables with comments.
