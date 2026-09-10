# jeelink2mqtt

A smart home app to read in values of Jeelink temperature and humidity sensors.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework, currently
on the 0.9.4 release.

## Home Assistant Discovery

**Wired up.** `jeelink2mqtt.main` calls `app.discovery()` (ADR-004, ADR-059), so on the
first successful MQTT connect the app publishes retained
`homeassistant/<component>/jeelink2mqtt/.../config` payloads generated from its own
live, already-expanded registry. Nothing to configure in Home Assistant — the sensors
appear automatically. Removing a sensor from `settings.sensors` clears its retained
discovery topics on the next start, the same way `state`/`availability` are cleaned up
(ADR-048).

Each configured sensor (`settings.sensors`) is registered as its own `@app.device`
entity — a callable `NameSpec` keyed by `settings.sensors` (cap-ayy) — with
framework-managed availability, ADR-048 retained-entity cleanup, and validated state
(`SensorStateModel`, ADR-046). The `x-cosalette-consumer` metadata on that model's
`temperature`, `humidity` and `low_battery` fields (cap-egy) turns into three HA
entities per sensor:

| Field         | HA entity                                   | Topic                       |
| ------------- | ------------------------------------------- | --------------------------- |
| `temperature` | `sensor`, `device_class: temperature`, `°C` | `jeelink2mqtt/{name}/state` |
| `humidity`    | `sensor`, `device_class: humidity`, `%`     | `jeelink2mqtt/{name}/state` |
| `low_battery` | `binary_sensor`, `device_class: battery`    | `jeelink2mqtt/{name}/state` |

Because `app.discovery()` reads the runtime registry rather than the checked-in
`docs/schema.yaml`, settings-derived sensor names are always correct without a
representative `.env.schema` profile. `docs/schema.yaml` and
`task jeelink2mqtt:schema:check` stay as the openHAB (`cosalette schema openhab`) and
drift-gate path; `task jeelink2mqtt:schema:ha-discovery` remains available for offline
inspection of the same payloads.

jeelink2mqtt sensors are configured by logical name — the set of sensor names is static,
fixed at configuration time. Only the ephemeral LaCrosse radio ID behind each name is
resolved at runtime, via auto-adopt (ADR-002), which binds an incoming radio ID to an
_already-configured_ sensor name and never invents a new one — so there is no dynamic
entity set to worry about.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
