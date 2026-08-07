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

`cosalette schema check` (the CI gate, `task velux2mqtt:schema:check`) still cannot
validate this app — it has no `--resolve-settings` support and unconditionally rejects
any settings-derived NameSpec at import time (cap-wv9 part b, blocked on upstream); the
task explicitly skips it with a message referencing cap-44e/cap-0cg rather than failing
CI unexplained. See `packages/tests/integration/test_schema_discovery.py`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
