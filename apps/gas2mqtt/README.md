# gas2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes counter
ticks, temperature, and optional raw debug data to MQTT.

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework.

> **📖 [Full Documentation](https://ff-fab.github.io/gas2mqtt/)**

## Features

- Gas tick detection via Schmitt trigger with configurable thresholds
- Temperature monitoring with EWMA filter and empirical calibration
- Optional raw magnetometer debug device
- Optional gas consumption tracking (m³)
- Automatic MQTT health reporting (heartbeats, LWT, availability)
- Docker deployment ready

## Hardware

- **Sensor:** QMC5883L 3-axis digital magnetometer
- **Interface:** I2C (default bus 1, address 0x0D)
- **Target:** Raspberry Pi (or any Linux SBC with I2C)

## Quick Start

```bash
git clone https://github.com/ff-fab/gas2mqtt.git
cd gas2mqtt
cp .env.example .env    # edit with your MQTT broker settings
docker compose up -d
```

See the [Getting Started guide](https://ff-fab.github.io/gas2mqtt/getting-started/) for
Docker and manual install options, wiring instructions, and first-run verification.

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
