# airthings2mqtt

Reads Airthings Wave air quality sensors over BLE and publishes temperature, humidity,
and radon data to MQTT.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Automatic.** Discovery config payloads publish to `homeassistant/.../config`
(retained) on the first successful MQTT connect — one `sensor` per reading field
(temperature, humidity, radon 24h avg, radon long-term avg), no manual copy step.
Entities removed since the last run are cleared automatically.

See the composition root (`packages/src/airthings2mqtt/main.py`, monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)) and
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
