# gas2mqtt

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)

Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes counter
ticks, temperature, and optional raw debug data to MQTT.

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework.

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

### Docker (recommended)

```bash
# Clone and configure
git clone https://github.com/ff-fab/gas2mqtt.git
cd gas2mqtt
cp .env.example .env
# Edit .env with your MQTT broker and sensor settings

# Start gas2mqtt + Mosquitto
docker compose up -d
```

The container needs I2C host access (`/dev/i2c-1`), which `docker-compose.yml` maps
automatically.

### Manual

```bash
pip install gas2mqtt   # or: uv add gas2mqtt
gas2mqtt               # reads .env or environment variables
```

## Configuration

All settings are loaded from environment variables (`GAS2MQTT_` prefix), `.env` files,
or CLI flags. Priority: CLI > env > `.env` > defaults.

| Setting              | Env Variable                           | Default     | Description                           |
| -------------------- | -------------------------------------- | ----------- | ------------------------------------- |
| MQTT host            | `GAS2MQTT_MQTT__HOST`                  | `localhost` | MQTT broker hostname                  |
| MQTT port            | `GAS2MQTT_MQTT__PORT`                  | `1883`      | MQTT broker port                      |
| MQTT username        | `GAS2MQTT_MQTT__USERNAME`              | —           | Broker username                       |
| MQTT password        | `GAS2MQTT_MQTT__PASSWORD`              | —           | Broker password                       |
| I2C bus              | `GAS2MQTT_I2C_BUS`                     | `1`         | I2C bus number                        |
| I2C address          | `GAS2MQTT_I2C_ADDRESS`                 | `13` (0x0D) | QMC5883L address                      |
| Trigger level        | `GAS2MQTT_TRIGGER_LEVEL`               | `-5000`     | Bz trigger threshold                  |
| Trigger hysteresis   | `GAS2MQTT_TRIGGER_HYSTERESIS`          | `700`       | Hysteresis band                       |
| Poll interval        | `GAS2MQTT_POLL_INTERVAL`               | `1.0`       | Sensor poll interval (seconds)        |
| Temperature interval | `GAS2MQTT_TEMPERATURE_INTERVAL`        | `300.0`     | Temperature report interval (seconds) |
| Temp scale           | `GAS2MQTT_TEMP_SCALE`                  | `0.008`     | Temperature calibration scale         |
| Temp offset          | `GAS2MQTT_TEMP_OFFSET`                 | `20.3`      | Temperature calibration offset        |
| EWMA alpha           | `GAS2MQTT_EWMA_ALPHA`                  | `0.2`       | Smoothing factor (0–1)                |
| Consumption tracking | `GAS2MQTT_ENABLE_CONSUMPTION_TRACKING` | `false`     | Enable m³ tracking                    |
| Liters per tick      | `GAS2MQTT_LITERS_PER_TICK`             | `10.0`      | Gas liters per tick                   |
| Debug device         | `GAS2MQTT_ENABLE_DEBUG_DEVICE`         | `false`     | Enable raw magnetometer output        |

See [.env.example](.env.example) for a ready-to-copy template.

## MQTT Topics

| Topic                                | Direction | Payload                                                             | Retain |
| ------------------------------------ | --------- | ------------------------------------------------------------------- | ------ |
| `gas2mqtt/gas_counter/state`         | outbound  | `{"counter": N, "trigger": "OPEN"\|"CLOSED", "consumption_m3"?: N}` | yes    |
| `gas2mqtt/gas_counter/set`           | inbound   | `{"consumption_m3": N}`                                             | —      |
| `gas2mqtt/gas_counter/availability`  | outbound  | `"online"` / `"offline"`                                            | yes    |
| `gas2mqtt/temperature/state`         | outbound  | `{"temperature": N}`                                                | yes    |
| `gas2mqtt/temperature/availability`  | outbound  | `"online"` / `"offline"`                                            | yes    |
| `gas2mqtt/magnetometer/state`        | outbound  | `{"bx": N, "by": N, "bz": N}`                                       | yes    |
| `gas2mqtt/magnetometer/availability` | outbound  | `"online"` / `"offline"`                                            | yes    |
| `gas2mqtt/status`                    | outbound  | Heartbeat JSON + LWT `"offline"`                                    | yes    |
| `gas2mqtt/error`                     | outbound  | Error JSON                                                          | no     |

## Architecture

```
ports.py          ← MagnetometerPort protocol (hardware boundary)
adapters/         ← qmc5883l.py (production I2C) · fake.py (test/dry-run)
domain/           ← schmitt.py · ewma.py · consumption.py (pure logic)
devices/          ← gas_counter · temperature · magnetometer (cosalette devices)
settings.py       ← Pydantic settings, extends cosalette.Settings
main.py           ← App factory, lifespan, adapter + device wiring
```

The codebase follows a **ports-and-adapters** (hexagonal) architecture. Domain logic has
zero I/O dependencies. The cosalette framework handles MQTT connectivity, health
reporting, error isolation, and graceful shutdown.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
