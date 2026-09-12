# Configuration

wiz2mqtt uses `pydantic-settings` for configuration. Settings resolve in this
order:

1. CLI flags
2. Environment variables with the `WIZ2MQTT_` prefix
3. A `.env` file in the working directory
4. `wiz2mqtt.toml` for the bulb and group inventory
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

## Groups

Optional `[[groups]]` entries keep consumer-side membership beside the bulbs:

```toml
[[groups]]
name = "ceiling"
members = ["desk", "lamp"]
```

Names use `[A-Za-z0-9_-]+` (at most 64 characters), must be unique, and cannot
collide with bulb names. Each group needs at least one member; members must be
distinct, declared bulb names. A bulb can belong to multiple groups.

Groups create no MQTT entities or topics and do not change Home Assistant
discovery. They are rendered only for openHAB; HA groups remain HA configuration.

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
Compose override when your broker expects TLS.

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

Consumer wiring is derived from the bulb inventory and optional group membership.

### Home Assistant discovery

`main` calls `app.discovery()`, so on the first successful MQTT connect wiz2mqtt
publishes retained `homeassistant/<component>/wiz2mqtt/.../config` payloads built
from its live registry. Each `[[bulbs]]` entry becomes one HA device with a
`light` (`schema: json`), an effect-speed `number`, and a power `sensor`; one
`binary_sensor` bridge entity is published for the app. Dropping a bulb from
`wiz2mqtt.toml` clears its retained discovery topics on the next start. Nothing in
Home Assistant needs configuring.

The `light` metadata is **capability-accurate per bulb**: `supported_color_modes`,
`effect_list`, and `min_kelvin`/`max_kelvin` reflect what each bulb actually
supports, so a tunable-white or dimmable-white bulb no longer shows an RGB picker
or effect list it cannot honour. Because bulb capabilities are auto-detected at
runtime — never declared in config — the accurate values are only known after
wiz2mqtt has contacted the bulb once. Discovery is published on connect, before
any bulb is reached, so a **freshly onboarded or newly swapped bulb advertises a
safe wire-format superset on its first run and the accurate, narrowed metadata
from the next restart onward** (see "Adding or replacing a bulb" in
[Getting Started](getting-started.md)). This is Mechanism B in
[ADR-003](adr/ADR-003-toml-inventory-as-the-configuration-boundary.md).

### openHAB generation

For your deployment, run from the repository root:

```bash
task wiz2mqtt:openhab -- --config-file wiz2mqtt.toml --output things > wiz2mqtt.things
task wiz2mqtt:openhab -- --config-file wiz2mqtt.toml --output items > wiz2mqtt.items
```

The config path is relative to `apps/wiz2mqtt/`; an absolute path also works.
Installed deployments can run `wiz2mqtt-openhab` with the same options.
Use `--broker-uid <id>` to match your openHAB MQTT broker Thing (default `broker`).
Install the outputs in openHAB's `things/` and `items/` directories.

This command resolves the actual TOML inventory through cosalette's schema CLI
without contacting bulbs or MQTT. Each group becomes one plain openHAB `Group`
whose members are the bulbs' Color command Items. openHAB fans on/off, dimming,
and HSB color commands out through their existing MQTT channels. Groups have no
aggregate state; individual telemetry Items remain available for state display.
Effect and color-temperature commands are not added to these groups. See
[openHAB Items](https://www.openhab.org/docs/configuration/items) for group semantics.
Regenerate both files after inventory or membership changes. Names that collapse
to the same openHAB identifier are rejected by the deployment generator.

`task wiz2mqtt:schema:openhab` renders a Generic MQTT Thing and matching Items
file from the checked-in sample `docs/schema.yaml`; it does not use deployment
groups. Both paths are offline only; wiz2mqtt never talks to openHAB at
runtime. Regenerate `docs/schema.yaml` with `task wiz2mqtt:schema:generate --yes`
after changing the state model; `task wiz2mqtt:schema:check` is the drift gate.
See [mqtt-topics.md](mqtt-topics.md) for the channel layout.
