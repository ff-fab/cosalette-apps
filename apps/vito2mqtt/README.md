# vito2mqtt

A smart home app to control a Vitodens gas heating.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant

**Automatic.** Home Assistant discovery config payloads publish to
`homeassistant/.../config` (retained) on the first successful MQTT connect — boiler
temperature, modulation, burner statistics, and pump sensors appear without any manual
setup step. Entities removed since the last run are cleared automatically.

See the composition root (`packages/src/vito2mqtt/main.py`, monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)) and
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## References

- [pyvcontrol](https://github.com/joppi588/pyvcontrol/tree/master) — Python library for
  Viessmann heating control, including P300 protocol implementation — used as a
  reference for protocol behavior and data type encoding rules

## License

This program is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE)
for details.
