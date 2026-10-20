# Getting Started

This guide connects a Geiger counter board to a Raspberry Pi and starts geiger2mqtt
with Docker Compose.

## Wiring

geiger2mqtt counts falling edges on one GPIO pin, BCM 4 by default.

| Board        | Raspberry Pi                     |
| ------------ | -------------------------------- |
| Signal output | BCM 4 (physical pin 7)          |
| GND          | Any GND pin (for example pin 9)  |

!!! caution

    Measure the idle voltage of the board output before you connect it. If it is 5 V, use a level shifter or a voltage divider. The GPIO pins of the Pi are not 5 V tolerant.

To use another pin, set `GEIGER2MQTT_GPIO_PIN` to its BCM number.

### Pull-up

Most boards drive their output high between pulses, so the pin needs no pull-up and
`GEIGER2MQTT_GPIO_PULL_UP` stays `false`. If the board has an open-collector output
that only pulls the line low, set `GEIGER2MQTT_GPIO_PULL_UP=true` to enable the Pi's
internal pull-up resistor.

## GPIO access

The container reads `/dev/gpiochip0` as a non-root user. On the host, that device
belongs to the `gpio` group. The image has no group of that name, so Compose adds the
host's group by its numeric ID. The ID is assigned when the system is installed and
differs between installations, so look it up:

```bash
getent group gpio
# gpio:x:997:pi
```

The third field is the GID. Compose uses `997` unless you set
`GEIGER2MQTT_GPIO_GID` in `.env`.

## Run with Docker Compose

```bash
cd apps/geiger2mqtt
cp .env.example .env
# Edit .env: GPIO GID, pin, conversion factor for your tube
docker compose up -d
```

`compose.yml` starts geiger2mqtt and a bundled Mosquitto broker that listens on
`127.0.0.1:1883`. To use your own broker, set `GEIGER2MQTT_MQTT__HOST` in the
`environment` block of `compose.yml` and remove the `mosquitto` service.

## First messages

geiger2mqtt counts for 60 seconds before it publishes the first reading:

```bash
mosquitto_sub -h localhost -t 'geiger2mqtt/#' -v
```

```text
geiger2mqtt/radiation/state {"cpm": 21, "dose_rate": 0.1197, "dose_rate_avg": 0.1197}
```

See [MQTT Topics](mqtt-topics.md) for all topics and [Configuration](configuration.md)
for all settings.

## Try it without hardware

`--dry-run` replaces the GPIO pin with a simulated counter at 20 CPM:

```bash
uv run --package geiger2mqtt geiger2mqtt --dry-run
```
