# Getting Started

wiz2mqtt publishes WiZ bulb state to MQTT and accepts partial JSON commands on
each bulb's `.../set` topic.

## Prerequisites

- Python 3.14 and the workspace dependencies installed
- A reachable MQTT broker
- One or more WiZ bulbs on the same LAN, ideally with stable IPv4 addresses

## 1. Configure the bulb inventory

Create `wiz2mqtt.toml` and list each bulb as a TOML array item:

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

`name` becomes the MQTT topic segment (`wiz2mqtt/<name>/...`). `mac` is optional
but useful when you want startup verification that the configured IP still
belongs to the intended bulb.

## 2. Point the app at your broker

Set the MQTT broker details with environment variables or a `.env` file:

```bash
export WIZ2MQTT_MQTT__HOST=mosquitto
export WIZ2MQTT_MQTT__PORT=1883
```

If your broker requires TLS, opt in explicitly:

```bash
export WIZ2MQTT_MQTT__TLS=true
```

## 3. Start the bridge

From the repo root:

```bash
uv run --package wiz2mqtt wiz2mqtt
```

## 4. Verify state and commands

With the default topic prefix, each bulb exposes:

- `wiz2mqtt/<bulb>/state` - retained JSON state
- `wiz2mqtt/<bulb>/set` - inbound partial-update command payloads
- `wiz2mqtt/<bulb>/availability` - `online` / `offline`

See [mqtt-topics.md](mqtt-topics.md) for concrete payload examples.

## 5. Adding or replacing a bulb

### Add a new bulb

1. Find the bulb's IP. The bundled discovery helper broadcasts for WiZ bulbs on
   the LAN and prints paste-ready `[[bulbs]]` blocks:

   ```console
   $ uv run --package wiz2mqtt wiz2mqtt-discover --wait 5 > discovered.toml
   ```

   Rename each placeholder `name` to something meaningful and pin the bulb's
   address with a static DHCP reservation (wiz2mqtt addresses bulbs by `ip`).

2. Add the `[[bulbs]]` entry to `wiz2mqtt.toml` and restart wiz2mqtt. The bulb
   appears in Home Assistant automatically (retained MQTT discovery) — no HA-side
   configuration needed.

!!! note "Home Assistant controls settle after the next restart"

    Home Assistant discovery is published the moment wiz2mqtt connects, which is
    _before_ it has talked to the new bulb. So on a bulb's **first run** wiz2mqtt
    advertises a safe superset of controls (RGB picker, full effect list, the
    widest colour-temperature range). It detects the bulb's real capabilities on
    first contact and, from the **next restart onward**, advertises only what
    that bulb actually supports. A tunable-white or dimmable-white bulb briefly
    over-offers controls until then; commands it cannot honour are ignored, so
    nothing breaks in the meantime.

### Advertise a change of bulb type

If you physically swap a bulb for a different model at the same `name`/`ip` (for
example an RGB bulb replaced by a tunable-white one), wiz2mqtt notices the new
capabilities the next time it contacts the bulb. To make Home Assistant show the
new bulb's controls:

1. Restart wiz2mqtt and let it run long enough to reach the bulb (a few seconds —
   watch for the bulb going `online`). This refreshes the cached capabilities.
2. Restart wiz2mqtt once more. The updated `light` entity is now advertised with
   the new bulb's colour modes, effect list, and Kelvin range.

The two-step restart exists because discovery is published on connect: the first
restart records what changed, the second publishes it. Capabilities are never
written into `wiz2mqtt.toml` — they are always re-detected from the bulb, so the
inventory file never goes stale against the hardware.
