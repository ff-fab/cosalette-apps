# velux2mqtt

Control Velux covers via KLF 050 remotes and M74HC4066 GPIO switches

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Currently non-functional — this is a regression, not a design gap.** Running
`task velux2mqtt:schema:ha-discovery` yields an empty payload list `[]`.

Covers are registered via `app.device(name=_cover_map, ...)`, a callable `name=` keyed
off user-configured `settings.covers` (each deployment defines its own cover names, e.g.
`blind`, `window`). cosalette's static schema pipeline has no way to see those
per-deployment names ahead of time, so it collapses every cover into a single schema
channel named after the Python handler's qualname (`cover_device`). If that channel
carried Home Assistant consumer metadata, `cosalette schema ha-discovery` would emit a
payload whose `state_topic` (`velux2mqtt/cover_device/state`) matches no topic any
running cover actually publishes to (real topics are `velux2mqtt/{cover}/state`, e.g.
`velux2mqtt/blind/state` — see [MQTT Topics](docs/mqtt-topics.md)) — registering a
permanently-unavailable phantom entity in Home Assistant.

`CoverState.position` therefore deliberately carries no `x-cosalette-consumer`
annotation, so no discovery payload is generated at all. Cover names can't be hardcoded
as a workaround since they're genuinely per-deployment. This will be re-enabled once
cosalette's schema pipeline resolves callable-`name=` NameSpecs to per-instance channels
(tracked upstream); see `packages/tests/integration/test_schema_discovery.py` for the
regression guard.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
