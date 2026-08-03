# jeelink2mqtt

A smart home app to read in values of Jeelink temperature and humidity sensors.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Not applicable.** This app does not emit Home Assistant MQTT discovery payloads, and
its `docs/schema.yaml` carries no `x-cosalette-consumer` annotations (running
`task jeelink2mqtt:schema:ha-discovery` yields an empty payload list `[]`).

jeelink2mqtt sensors are configured by logical name (`settings.sensors`) — the set of
sensor names is static, fixed at configuration time. Only the ephemeral LaCrosse radio
ID behind each name is resolved at runtime, via auto-adopt (ADR-002): auto-adopt binds
an incoming radio ID to an _already-configured_ sensor name and never invents a new one,
so there is no dynamic entity set here to worry about.

The actual reason HA discovery doesn't work is simpler: jeelink2mqtt doesn't register
any framework entities at all. The `receiver` handler (an `@app.stream`) publishes
readings via ad-hoc `ctx.publish(f"{name}/state", ...)` and
`ctx.publish(f"{name}/availability", ...)` string-built topics from inside the stream
loop, rather than through `@app.telemetry`/`@app.device`/`@app.command`. cosalette's HA
discovery generator (`cosalette schema ha-discovery`) works by walking the static
AsyncAPI schema registry built from decorator introspection — with no per-sensor
registration, there is nothing in that registry to annotate. This holds regardless of
archetype: `@app.stream` is deliberately narrower than `@app.device`/`@app.telemetry` by
design (it isn't a fourth entity-bearing archetype, and was never disqualified from
schema generation by some inherent "dynamic per-sensor topic" property — jeelink2mqtt's
topics aren't actually dynamic).

Migrating to registered telemetry entities (a callable `NameSpec` keyed by
`settings.sensors`, one entity per configured sensor) is possible and would bring other
benefits — framework-managed availability, ADR-048 retained-entity cleanup on sensor
removal, framework online/offline lifecycle publishing (tracked in cap-ayy). It would
**not**, by itself, produce working HA discovery: settings-derived entity names can't
currently be represented in the static AsyncAPI artifact that `schema:ha-discovery`
walks. That's a separate, upstream-tracked limitation — see cap-wv9 for the
settings-aware schema pipeline work that would actually be needed to unblock this.

Home Assistant can still consume jeelink2mqtt's sensors today via manually-configured
[MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/) entities pointed
at `jeelink2mqtt/{name}/state` (JSON `temperature`/`humidity`/`low_battery` fields) and
`jeelink2mqtt/{name}/availability`. See cap-dnw for the full analysis.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
