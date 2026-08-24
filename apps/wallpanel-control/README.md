# wallpanel-control

MQTT bridge for controlling a wall-panel display and system via SSH and Wake-on-LAN.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant

**Automatic.** Home Assistant discovery config payloads publish to
`homeassistant/.../config` (retained) on the first successful MQTT connect — the display
entity appears without any manual setup step. Entities removed since the last run are
cleared automatically.

See the composition root (`packages/src/wallpanel_control/main.py`, monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)) and
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
