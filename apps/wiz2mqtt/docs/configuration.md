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
| TLS | `WIZ2MQTT_MQTT__TLS` | `true` (set to `false` by the shipped deployment) |

Transport security is a per-deployment setting. cosalette defaults `tls` to
`true`; the shipped `compose.yml` defaults `WIZ2MQTT_MQTT__TLS` to `false` for
its bundled plaintext broker. Set `WIZ2MQTT_MQTT__TLS=true` in `.env` or a
Compose override when your broker expects TLS. See
[ADR-006](https://ff-fab.github.io/cosalette-apps/adr/ADR-006-mqtt-transport-security-posture/).

## Config-file and environment interplay

The TOML file owns the bulb inventory, while environment variables are the
usual place for deployment-specific MQTT details. Environment variables outrank
the config file, so `WIZ2MQTT_MQTT__HOST=broker.local` overrides any broker
settings implied elsewhere without rewriting `wiz2mqtt.toml`.

## Publication Behaviour

Publication is push-driven and has no configuration surface. State reaches MQTT
when the bulb sends a UDP push; the 60-second `interval=` tick is a heartbeat
and liveness probe rather than the publication driver.

Two related values are fixed constants in the code, not settings:

| Value | Where | Behaviour |
| ----- | ----- | --------- |
| Heartbeat tick, 60 s | `main._TICK_INTERVAL_SECONDS` | Refreshes idle bulbs and re-checks availability |
| Push-staleness threshold, 60 s | `adapters.wizlight._DEFAULT_PUSH_STALENESS_THRESHOLD` | A read falls back to polling the bulb when the last push is older than this |

They are deliberately equal: a bulb only pushes on *change*, so a healthy but
idle bulb produces no traffic, and every heartbeat tick finds the push cache
stale and polls once.

The bulb entity is declared `triggerable="local"`, so the wake is in-process
only — wiz2mqtt subscribes **no** trigger topic. The only inbound topic is each
bulb's `set` command topic documented in
[mqtt-topics.md](mqtt-topics.md).

## Consumer Integration

wiz2mqtt has no configuration surface for consumer wiring — it renders from the
bulb inventory automatically.

### Home Assistant discovery

`main` calls `app.discovery()`, so on the first successful MQTT connect wiz2mqtt
publishes retained `homeassistant/<component>/wiz2mqtt/.../config` payloads built
from its live registry. Each `[[bulbs]]` entry becomes one HA device with a
`light` (`schema: json`), an effect-speed `number`, and a power `sensor`; one
`binary_sensor` bridge entity is published for the app. Dropping a bulb from
`wiz2mqtt.toml` clears its retained discovery topics on the next start. Nothing in
Home Assistant needs configuring. The `light` metadata is a static wire-format
superset (`supported_color_modes: [color_temp, rgb]`, the full 38-scene
`effect_list`, `min_kelvin`/`max_kelvin` 2200–6500); runtime auto-detection still
gates command handling. Per-bulb capability filtering is deferred (`cap-3tr`,
[ADR-003](adr/ADR-003-toml-inventory-as-the-configuration-boundary.md)).

Inspect the payloads offline with `task wiz2mqtt:schema:ha-discovery`.

### openHAB generation

`task wiz2mqtt:schema:openhab` renders a Generic MQTT Thing and matching Items
file from `docs/schema.yaml` — offline only, wiz2mqtt never talks to openHAB at
runtime. Regenerate `docs/schema.yaml` with `task wiz2mqtt:schema:generate --yes`
after changing the state model; `task wiz2mqtt:schema:check` is the drift gate.
See [mqtt-topics.md](mqtt-topics.md) for the channel layout.
