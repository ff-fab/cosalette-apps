# wiz2mqtt

WiZ smart bulb control over MQTT for openHAB and Home Assistant

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Wired up.** `wiz2mqtt.main` calls `app.discovery()` (monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)), so on
the first successful MQTT connect the app publishes retained
`homeassistant/<component>/wiz2mqtt/.../config` payloads generated from its own live,
already-expanded registry. Nothing to configure in Home Assistant — each configured bulb
appears automatically as one device. Removing a bulb from `wiz2mqtt.toml` clears its
retained discovery topics on the next start.

Each `[[bulbs]]` entry becomes one HA **device** carrying three entities, all reading
the one retained `wiz2mqtt/{name}/state` payload:

| Entity       | HA component            | Key fields                                                                                                                       | Topics                                                       |
| ------------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Light        | `light`, `schema: json` | `brightness`, `supported_color_modes: [color_temp, rgb]`, `effect` + 38-scene `effect_list`, `min_kelvin`/`max_kelvin` 2200–6500 | state `wiz2mqtt/{name}/state`, command `wiz2mqtt/{name}/set` |
| Effect speed | `number`                | `min` 10, `max` 200, `step` 1, `command_template` `{"effect_speed": {{ value }}}`                                                | state `wiz2mqtt/{name}/state`, command `wiz2mqtt/{name}/set` |
| Power        | `sensor`                | `device_class: power`, `unit_of_measurement: W`, `state_class: measurement`                                                      | state `wiz2mqtt/{name}/state` (read-only)                    |

One bridge-level `binary_sensor` (`device_class: connectivity`, state topic
`wiz2mqtt/status`) is published once for the whole app.

The `light` discovery metadata is a **static wire-format superset** — every bulb
advertises `color_temp` + `rgb` and the full scene list regardless of its actual class.
Runtime capability auto-detection still governs which commands the adapter forwards, so
a control that a given bulb lacks is a no-op, never a mis-routed command. Per-bulb
capability-filtered discovery metadata is deferred (`cap-3tr`; see
[ADR-003](docs/adr/ADR-003-toml-inventory-as-the-configuration-boundary.md)).

Because `app.discovery()` reads the runtime registry rather than the checked-in
`docs/schema.yaml`, bulb names are always correct without a representative `.env.schema`
profile. `docs/schema.yaml` and `task wiz2mqtt:schema:check` stay as the openHAB
(`cosalette schema openhab`) and drift-gate path; `task wiz2mqtt:schema:ha-discovery`
remains available for offline inspection of the same payloads. See
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for setup instructions, common commands,
project structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
