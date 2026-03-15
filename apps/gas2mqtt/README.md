# gas2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)
[![ghcr.io](https://img.shields.io/badge/container-ghcr.io%2Fff--fab%2Fgas2mqtt-blue)](https://github.com/ff-fab/gas2mqtt/pkgs/container/gas2mqtt)

Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes counter
ticks, temperature, and optional raw debug data to MQTT.

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework.

> **📖 [Full Documentation](https://ff-fab.github.io/gas2mqtt/)**

## Quick Start

Create a directory on your Raspberry Pi and add this `docker-compose.yml`:

```yaml
services:
  gas2mqtt:
    image: ghcr.io/ff-fab/gas2mqtt:latest
    restart: unless-stopped
    devices:
      - /dev/i2c-1:/dev/i2c-1
    group_add:
      - i2c
    env_file: .env
    environment:
      GAS2MQTT_MQTT__HOST: mosquitto
    volumes:
      - gas2mqtt-data:/app/data
    depends_on:
      - mosquitto

  mosquitto:
    image: eclipse-mosquitto:2
    restart: unless-stopped
    ports:
      - '1883:1883'
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log

volumes:
  gas2mqtt-data:
  mosquitto-data:
  mosquitto-log:
```

Then fetch the supporting files and start:

```bash
curl -fsSL https://raw.githubusercontent.com/ff-fab/gas2mqtt/main/mosquitto.conf -o mosquitto.conf
curl -fsSL https://raw.githubusercontent.com/ff-fab/gas2mqtt/main/.env.example -o .env
# Edit .env — set GAS2MQTT_MQTT__HOST and sensor thresholds
docker compose up -d
```

See the [Getting Started guide](https://ff-fab.github.io/gas2mqtt/getting-started/) for
wiring instructions, first-run verification, and manual install options.

## Features

- Gas tick detection via Schmitt trigger with configurable thresholds
- Temperature monitoring with PT1 filter and empirical calibration
- Optional raw magnetometer debug device
- Optional gas consumption tracking (m³)
- Automatic MQTT health reporting (heartbeats, LWT, availability)
- Multi-arch container image (`linux/amd64`, `linux/arm64`)

## Hardware

- **Sensor:** QMC5883L 3-axis digital magnetometer
- **Interface:** I2C (default bus 1, address 0x0D)
- **Target:** Raspberry Pi 3/4/5 or Zero 2 W (or any Linux SBC with I2C)

## Configuration

All settings are loaded from environment variables (`GAS2MQTT_` prefix), `.env` files,
or CLI flags. See [.env.example](.env.example) for a ready-to-copy template.

See the [Configuration reference](https://ff-fab.github.io/gas2mqtt/configuration/) for
the full settings table with defaults and descriptions.

## MQTT Topics

gas2mqtt publishes to 9 MQTT topics covering gas counter state, temperature, optional
debug output, health/heartbeat, and error reporting. One topic accepts inbound commands.

See the [MQTT Topics reference](https://ff-fab.github.io/gas2mqtt/mqtt-topics/) for the
complete topic table with payload schemas.

## Architecture

The codebase follows a **ports-and-adapters** (hexagonal) architecture. Domain logic has
zero I/O dependencies. The cosalette framework handles MQTT connectivity, health
reporting, error isolation, and graceful shutdown.

See the [Architecture overview](https://ff-fab.github.io/gas2mqtt/architecture/) for
diagrams and detailed layer descriptions.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
