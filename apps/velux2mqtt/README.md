# velux2mqtt

Control Velux covers via KLF 050 remotes and M74HC4066 GPIO switches

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Automatic.** Discovery config payloads publish to `homeassistant/.../config`
(retained) on the first successful MQTT connect — no manual copy step. Covers appear as
one `cover` entity per configured cover, grouped per device under the app bridge entity.

The composition root calls `app.discovery()` (monorepo
[ADR-004](../../docs/adr/ADR-004-runtime-home-assistant-discovery-adoption.md)):
payloads are generated from the live registry after the callable `name=` spec has
resolved against `settings.covers`, so each payload's `state_topic` matches the real
runtime topic (`velux2mqtt/blind/state`, ... — see [MQTT Topics](docs/mqtt-topics.md)).
Entities for covers removed from the config are cleared automatically on the next
startup.

Covers are registered via `app.device(name=_cover_map, ...)`, a callable `name=` keyed
off user-configured `settings.covers` (each deployment defines its own cover names, e.g.
`blind`, `window`). A plain `cosalette schema init`/`check` can't see those
per-deployment names ahead of time and would collapse every cover into a single schema
channel named after the Python handler's qualname (`cover_device`) — which is why
`task velux2mqtt:schema:generate` instead runs
`cosalette schema dump --resolve-settings` (ADR-051) against the checked-in
`.env.schema` profile, resolving settings and expanding the NameSpec into real per-cover
channels (`blindState`, `windowState`, ...) before `docs/schema.yaml` is written.

`docs/schema.yaml` remains mandatory even with runtime publication: it feeds openHAB's
offline generation and the `cosalette schema check` CI drift gate
(`task velux2mqtt:schema:check`, which validates this app too — cosalette 0.6.0 extended
`--resolve-settings`/`--env-file` to `schema check`). See
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
