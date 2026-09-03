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
