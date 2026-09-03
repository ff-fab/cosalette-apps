# Configuration

wiz2mqtt uses `pydantic-settings` for configuration. Settings resolve in this
order:

1. CLI flags
2. Environment variables with the `WIZ2MQTT_` prefix
3. A `.env` file in the working directory
4. `wiz2mqtt.toml` for the bulb inventory
5. Built-in defaults

## Bulb Inventory

The bulb list lives in `wiz2mqtt.toml` as `[[bulbs]]` entries:

```toml
[[bulbs]]
name = "desk"
ip = "10.0.0.10"

[[bulbs]]
name = "lamp"
ip = "10.0.0.11"
mac = "a8bb5006033d"
when_unreachable = "off"
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | yes | MQTT topic segment for the bulb |
| `ip` | yes | Literal IPv4 address of the bulb |
| `mac` | no | Bare 12-hex-digit MAC used for identity verification |
| `when_unreachable` | no | `unavailable` (default) or `off` |

`when_unreachable = "off"` keeps the bulb available and publishes
`{"state": "OFF"}` when reads fail. The default `unavailable` path instead
marks the entity offline after repeated failures.

## MQTT Settings

wiz2mqtt inherits the standard cosalette MQTT settings as a nested `mqtt`
model. Common environment variables are:

| Setting | Environment Variable | Default |
| ------- | -------------------- | ------- |
| Host | `WIZ2MQTT_MQTT__HOST` | `localhost` |
| Port | `WIZ2MQTT_MQTT__PORT` | `1883` |
| Username | `WIZ2MQTT_MQTT__USERNAME` | unset |
| Password | `WIZ2MQTT_MQTT__PASSWORD` | unset |
| Topic prefix | `WIZ2MQTT_MQTT__TOPIC_PREFIX` | `wiz2mqtt` |
| TLS | `WIZ2MQTT_MQTT__TLS` | `false` |

The repo currently pins `tls = false` by default to preserve existing plaintext
LAN-broker deployments after cosalette 0.7.0 flipped its own default to
`true`. Set `WIZ2MQTT_MQTT__TLS=true` when your broker expects TLS.

## Config-file and environment interplay

The TOML file owns the bulb inventory, while environment variables are the
usual place for deployment-specific MQTT details. Environment variables outrank
the config file, so `WIZ2MQTT_MQTT__HOST=broker.local` overrides any broker
settings implied elsewhere without rewriting `wiz2mqtt.toml`.
