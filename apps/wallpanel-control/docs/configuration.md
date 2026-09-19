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
| TLS          | `WALLPANEL_CONTROL_MQTT__TLS`           | `true` (see note)   | Enable TLS for broker connection |
| TLS CA file  | `WALLPANEL_CONTROL_MQTT__TLS_CA_FILE`   | --                  | CA bundle for broker certificate verification |
| TLS cert     | `WALLPANEL_CONTROL_MQTT__TLS_CERT_FILE` | --                  | Client certificate for mutual TLS |
| TLS key      | `WALLPANEL_CONTROL_MQTT__TLS_KEY_FILE`  | --                  | Client private key for mutual TLS |
| Protocol version | `WALLPANEL_CONTROL_MQTT__PROTOCOL_VERSION` | `3.1.1` in code, `5` in compose | `5` enables retained-message expiry and refresh, `3.1.1` disables both; see below |
| Message expiry | `WALLPANEL_CONTROL_MQTT__MESSAGE_EXPIRY_INTERVAL` | `86400` | Expiry of retained messages in seconds, at least `3`; valid only with protocol `5` |

!!! tip "Secure broker connections"
    Set `WALLPANEL_CONTROL_MQTT__TLS=true` when connecting to a broker outside
    localhost. Provide `TLS_CA_FILE` to verify the broker's certificate.
    For mutual TLS (client authentication), also set `TLS_CERT_FILE` and
    `TLS_KEY_FILE`. See `.env.example` for commented examples.

!!! note "Why the shipped deployment defaults to `false`"
    cosalette defaults `MqttSettings.tls` to `true` (ADR-062). This app keeps
    that default in code and states its transport posture in deployment config
    instead: `compose.yml` defaults `WALLPANEL_CONTROL_MQTT__TLS` to `false`
    for its bundled plaintext broker. Set `WALLPANEL_CONTROL_MQTT__TLS=true`
    in `.env` or a Compose override once the broker has a TLS listener.

!!! info "Double-underscore delimiter"
    MQTT settings are **nested** inside the settings model. Environment variables use
    `__` (double underscore) to separate nesting levels:

    `WALLPANEL_CONTROL_MQTT__HOST` -> `settings.mqtt.host`

    This is a [pydantic-settings convention](https://docs.pydantic.dev/latest/concepts/pydantic_settings/#parsing-environment-variable-values)
    for nested models.

### MQTT 5 retained-message expiry

The shipped `compose.yml` connects wallpanel-control with MQTT 5. Every retained message
it publishes carries a _Message Expiry Interval_ of `MESSAGE_EXPIRY_INTERVAL` seconds
(default `86400`, 24 hours): the display and system action state, availability, Home
Assistant discovery, `status`, `_meta/*` and the last will. While wallpanel-control
runs, it re-publishes each retained topic every third of that interval (default 8
hours), so the topics stay alive. A topic that nothing refreshes any more, such as a
stopped process, disappears from the broker by itself.

!!! note "State survives a restart"
    wallpanel-control publishes `display/state` and `system/action/state` only as the
    answer to a command, and nothing polls the panel. It saves each answer in the store
    and publishes the saved answers again, retained, at every startup. A subscriber that
    connects later, and the Home Assistant light, keep the last known state. The saved
    answer is not a new reading: it does not show a change that someone made at the panel
    while wallpanel-control was down.

**Operator contract**

- **The broker must support MQTT 5.** The bundled `eclipse-mosquitto:2` does. To check
  another broker, publish a retained message that expires and confirm it disappears:

  ```bash
  mosquitto_pub -V mqttv5 -r -t check/expiry -m hello -D publish message-expiry-interval 3
  sleep 5 && mosquitto_sub -V mqttv5 -t check/expiry -W 2   # prints nothing
  ```

- **There is no automatic fallback.** If the broker refuses MQTT 5, wallpanel-control
  logs `does the broker support MQTT 5?` and retries the connection. Set
  `WALLPANEL_CONTROL_MQTT__PROTOCOL_VERSION=3.1.1` to return to MQTT 3.1.1.
- **Expiry applies to new messages only.** Retained topics published before the switch
  never expire. Clear them by hand with an empty retained publish.
- **Keep the store on a volume.** The saved answers live in the file that
  `WALLPANEL_CONTROL_STORE_PATH` names (`/app/data/store.json` in the shipped
  `compose.yml`, on the `wallpanel_control-data` volume). Without a persistent store, a
  restart loses the answers and they expire after the expiry interval, until the next
  command.
- **Consumers see one repeat per refresh.** The repeat has the same payload as the last
  publish, and the broker forwards it to live subscribers without the retain flag, so it
  looks like a normal message. The repeat is not a new reading: it does not read the
  panel again. An automation that triggers on receipt of `system/action/state` runs once
  more per refresh; trigger on the command instead.
- **A repeat never runs an action.** wallpanel-control acts only on the `display/set`
  and `system/action/set` topics, which are never retained and never refreshed.
- **A long outage lets topics expire.** If wallpanel-control is down or disconnected for
  longer than the expiry interval, the broker drops its retained topics until the next
  publish.

### State store

| Setting    | Environment Variable           | Default                                        | Description                                                |
| ---------- | ------------------------------ | ---------------------------------------------- | ---------------------------------------------------------- |
| Store path | `WALLPANEL_CONTROL_STORE_PATH` | `$XDG_STATE_HOME/wallpanel-control/store.json` | File that holds the last display and system action answers |

The shipped `compose.yml` sets it to `/app/data/store.json` on the
`wallpanel_control-data` volume. See
[MQTT 5 retained-message expiry](#mqtt-5-retained-message-expiry) for why the file matters.

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
