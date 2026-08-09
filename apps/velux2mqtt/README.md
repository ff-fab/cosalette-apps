# velux2mqtt

Control Velux covers via KLF 050 remotes and M74HC4066 GPIO switches

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Functional.** Running `task velux2mqtt:schema:ha-discovery` emits one `sensor`
discovery payload per configured cover, with `state_topic` matching the real runtime
topic (e.g. `velux2mqtt/blind/state` — see [MQTT Topics](docs/mqtt-topics.md)).

Covers are registered via `app.device(name=_cover_map, ...)`, a callable `name=` keyed
off user-configured `settings.covers` (each deployment defines its own cover names, e.g.
`blind`, `window`). A plain `cosalette schema init`/`check` can't see those
per-deployment names ahead of time and would collapse every cover into a single schema
channel named after the Python handler's qualname (`cover_device`) — which is why
`task velux2mqtt:schema:generate` instead runs
`cosalette schema dump --resolve-settings` (ADR-051) against the checked-in
`.env.schema` profile, resolving settings and expanding the NameSpec into real per-cover
channels (`blindState`, `windowState`, ...) before `docs/schema.yaml` is written.
`CoverState.position` carries an `x-cosalette-consumer` annotation, so those real
channels do produce discovery payloads.

`cosalette schema check` (the CI gate, `task velux2mqtt:schema:check`) now validates
this app too: cosalette 0.6.0 extended `--resolve-settings`/`--env-file` to
`schema check` (previously dump-only, cap-wv9 part b), so the task runs it against the
same checked-in `.env.schema` profile. See
`packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
