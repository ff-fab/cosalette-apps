# cosalette-apps

A monorepo collection of IoT-to-MQTT bridge applications for smart home automation, all
built on the [cosalette](https://github.com/ff-fab/cosalette) framework.

[![CI](https://github.com/ff-fab/cosalette-apps/actions/workflows/ci.yml/badge.svg)](https://github.com/ff-fab/cosalette-apps/actions/workflows/ci.yml)
[![Docs](https://github.com/ff-fab/cosalette-apps/actions/workflows/docs.yml/badge.svg)](https://ff-fab.github.io/cosalette-apps/)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)
[![cosalette](https://img.shields.io/badge/framework-cosalette-orange)](https://github.com/ff-fab/cosalette)
[![REUSE](https://img.shields.io/badge/REUSE-compliant-green)](https://reuse.software/)

**[Documentation](https://ff-fab.github.io/cosalette-apps/)**

---

## What is cosalette-apps?

This monorepo consolidates multiple standalone IoT-to-MQTT bridge applications into a
single repository with shared tooling, CI, and release infrastructure. Each app reads
data from a physical sensor or device and publishes it to an MQTT broker for consumption
by Home Assistant or other home-automation systems.

All apps are built on [cosalette](https://github.com/ff-fab/cosalette), a Python
framework for IoT-to-MQTT applications that provides async MQTT lifecycle management,
decorator-based device registration, hexagonal architecture via PEP 544 Protocols, and
pydantic-settings integration.

## Apps

| App                                  | Description                                                                                                                            | License                                                                                              | Docs                                                                    |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| [caldates2mqtt](apps/caldates2mqtt/) | Reads CalDAV calendar dates and publishes upcoming all-day events to MQTT, with multi-calendar support and on-demand re-read commands. | [![MIT](https://img.shields.io/badge/MIT-blue)](apps/caldates2mqtt/LICENSE)                          | [Documentation](https://ff-fab.github.io/cosalette-apps/caldates2mqtt/) |
| [gas2mqtt](apps/gas2mqtt/)           | Reads a domestic gas meter using a QMC5883L magnetometer over I2C and publishes counter ticks, temperature, and debug data to MQTT.    | [![MIT](https://img.shields.io/badge/MIT-blue)](apps/gas2mqtt/LICENSE)                               | [Documentation](https://ff-fab.github.io/cosalette-apps/gas2mqtt/)      |
| [jeelink2mqtt](apps/jeelink2mqtt/)   | Bridges LaCrosse temperature and humidity sensors to MQTT via a JeeLink USB receiver.                                                  | [![MIT](https://img.shields.io/badge/MIT-blue)](apps/jeelink2mqtt/LICENSE)                           | [Documentation](https://ff-fab.github.io/cosalette-apps/jeelink2mqtt/)  |
| [vito2mqtt](apps/vito2mqtt/)         | Controls a Viessmann Vitodens gas boiler over the Optolink serial interface, publishing telemetry and accepting commands via MQTT.     | [![GPL-3.0-or-later](https://img.shields.io/badge/GPL--3.0--or--later-blue)](apps/vito2mqtt/LICENSE) | [Documentation](https://ff-fab.github.io/cosalette-apps/vito2mqtt/)     |

## Architecture

- **Framework:** [cosalette](https://github.com/ff-fab/cosalette) — async MQTT
  lifecycle, decorator-based device registration, hexagonal architecture
- **Build system:** [uv](https://docs.astral.sh/uv/) workspaces +
  [Taskfile](https://taskfile.dev/)
- **Licensing:** [REUSE](https://reuse.software/)-compliant (MIT default,
  GPL-3.0-or-later for vito2mqtt)
- **CI:** Per-app change detection with reusable workflows
- **Releases:** Release Please manifest mode (per-app versioning)
- **Docs:** [Zensical](https://zensical.squidfunk.com/) with per-app sub-sites

See [ADR-001](docs/adr/ADR-001-monorepo-structure.md) for the full decision record on
the monorepo structure.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, commands, project
structure, and code quality standards.

## License

This repository uses mixed licensing:

- **caldates2mqtt** is licensed under the [MIT License](apps/caldates2mqtt/LICENSE).
- **gas2mqtt** is licensed under the [MIT License](apps/gas2mqtt/LICENSE).
- **jeelink2mqtt** is licensed under the [MIT License](apps/jeelink2mqtt/LICENSE).
- **vito2mqtt** is licensed under [GPL-3.0-or-later](apps/vito2mqtt/LICENSE).
- Monorepo infrastructure and shared files are licensed under the
  [MIT License](LICENSE).

See [REUSE.toml](REUSE.toml) for the complete licensing breakdown.
