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
power_source = "lamp-power"
restore_previous_state = true
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | yes | MQTT topic segment for the bulb |
| `ip` | yes | Literal IPv4 address of the bulb |
| `mac` | no | Bare 12-hex-digit MAC verified on first successful contact; a mismatch rejects that contact, while a missing device MAC is warned as unverifiable |
| `power_source` | no | Name of a `[[power_sources]]` entry that powers this bulb directly. Wins over any `[[power_sources]]` block that claims the bulb's group (ADR-007) |
| `restore_previous_state` | no | Restore the bulb's previous desired state when it returns to reachability with no queued command (default `false`, ADR-008) |

### Legacy `when_unreachable` (bulb-level, removed)

The old bulb-level `when_unreachable` field was removed in favour of
`[[power_sources]]` (ADR-007). A `wiz2mqtt.toml` that still sets it is
migrated automatically at startup, with a warning logged for each bulb:

- `when_unreachable = "off"` becomes an implicit single-bulb power source
  (`name = "<bulb>-power"`, `members = ["<bulb>"]`,
  `when_unreachable = "no_power"`).
- `when_unreachable = "unavailable"` (the old default) is simply dropped —
  it is now the implicit default behaviour when no power source claims the
  bulb.
- Any other value still raises a validation error.

Update `wiz2mqtt.toml` to remove the bulb-level key and declare the
equivalent `[[power_sources]]` entry directly; the migration is a
compatibility shim, not a long-term feature.

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

## Power Sources

Optional `[[power_sources]]` entries model a mains circuit (ADR-007) that one
or more bulbs sit behind, e.g. a smart relay or wall switch feeding several
WiZ bulbs. This inventory and its validation are available now. Deriving or
publishing a `powered` belief, subscribing to `signal_topic`, and sending
power requests are reserved configuration only until their separately tracked
ADR-007/ADR-009 runtime work lands.

```toml
[[power_sources]]
name = "lamp-power"
members = ["lamp"]
when_unreachable = "no_power"

[[power_sources]]
name = "downstairs-power"
group = "downstairs"
signal_topic = "openhab/relay/downstairs/state"
when_unreachable = "fault"
enable_power_on_request = true
enable_power_off_request = true
power_off_idle_delay = 300
wiz_bulbs_only = true
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `name` | yes | Unique name, `[A-Za-z0-9_-]+`, at most 64 characters; must not collide with a bulb or group name |
| `group` | one of `group`/`members` | Name of an existing `[[groups]]` entry this source powers |
| `members` | one of `group`/`members` | Bulb names powered by this source directly |
| `signal_topic` | no | Reserved retained MQTT relay-signal topic (`on`/`off`); subscription is deferred until the ADR-007 runtime work lands |
| `when_unreachable` | no | What an unreachable member bulb means with no better evidence: `fault` (default, availability = offline) or `no_power` (bulb stays available, publishes `{"state": "OFF"}`) |
| `enable_power_on_request` | no | Reserve future power-on requests; runtime support is deferred (default `false`) |
| `enable_power_off_request` | no | Reserve future power-off requests; runtime support is deferred and requires `wiz_bulbs_only = true` (default `false`) |
| `power_off_idle_delay` | no | Reserved seconds every member bulb must be idle before a future power-off request; runtime support is deferred (default `600`) |
| `wiz_bulbs_only` | no | Operator declaration that every device on this circuit is a WiZ bulb wiz2mqtt controls; must be `true` before `enable_power_off_request` may be `true` (default `false`) |

Exactly one of `group` or `members` must be set. A bulb resolves to at most
one power source: its own `power_source` field (see [Bulb
Inventory](#bulb-inventory)) always wins over an implicit claim through
`members` or the bulb's group; two power sources implicitly claiming the
same bulb (through `members` and/or `group`) is a configuration error.

Like `[[bulbs]]` and `[[groups]]`, `power_sources` is TOML-only — there is no
environment-variable form.

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

## Command Queueing

| Setting | Environment Variable | Default | Description |
| ------- | --------------------- | ------- | ----------- |
| `queued_command_ttl` | `WIZ2MQTT_QUEUED_COMMAND_TTL` | `86400.0` (seconds) | Reserved command-queue TTL (ADR-008); queue runtime support is deferred, so this currently has no effect. |

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
| Heartbeat tick, 60 s | `main._TICK_INTERVAL_SECONDS` | Polls only when `last_push` is stale; otherwise reuses the push cache |
| Push-staleness threshold, 60 s | `adapters.wizlight._DEFAULT_PUSH_STALENESS_THRESHOLD` | A read falls back to polling the bulb when its own `last_push` clock is older than this |

They are deliberately equal, and the poll decision reads the bulb's own
`last_push` clock rather than the adapter's push-cache timestamp: a bulb
that keeps heartbeating (a syncPilot, changed or suppressed) proves its
own liveness, so no poll is needed while that traffic arrives. Only a
bulb that has gone genuinely silent for 60 s trips the fallback, and that
poll is then a real network read, not a no-op.

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
