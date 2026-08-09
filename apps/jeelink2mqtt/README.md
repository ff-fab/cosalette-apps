# jeelink2mqtt

A smart home app to read in values of Jeelink temperature and humidity sensors.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Not wired up yet**, but the blocker has changed. jeelink2mqtt now registers one
`@app.device` entity per configured sensor — a callable `NameSpec` keyed by
`settings.sensors` (cap-ayy) — instead of publishing state/availability via ad-hoc
`ctx.publish(f"{name}/state", ...)` string-built topics from inside the `@app.stream`
receiver loop. Each sensor gets framework-managed availability
(`ctx.mark_unavailable()`/`ctx.mark_available()`), ADR-048 retained-entity cleanup on
sensor removal, and validated state (`SensorStateModel`, ADR-046). Topics are unchanged:
`jeelink2mqtt/{name}/state` and `jeelink2mqtt/{name}/availability`.

`docs/schema.yaml` still carries no `x-cosalette-consumer` annotations and
`task jeelink2mqtt:schema:ha-discovery` still yields an empty payload list `[]`, because
that generator walks the _static_ AsyncAPI artifact built by import-time introspection —
and callable `NameSpec` registrations only expand to their real per-sensor names at
bootstrap (`app.run()`), not at import time. cosalette 0.6.0 added a settings-resolving
dump mode for exactly this case (ADR-051,
`schema dump/check/init --resolve-settings --env-file ...`), so per-entity discovery is
now technically possible — wiring it up for jeelink2mqtt (regenerating
`docs/schema.yaml` with the new flags, adding `consumer()` metadata to
`SensorStateModel` fields) is tracked as a separate follow-up, not yet done.

jeelink2mqtt sensors are configured by logical name (`settings.sensors`) — the set of
sensor names is static, fixed at configuration time. Only the ephemeral LaCrosse radio
ID behind each name is resolved at runtime, via auto-adopt (ADR-002): auto-adopt binds
an incoming radio ID to an _already-configured_ sensor name and never invents a new one,
so there is no dynamic entity set here to worry about.

Home Assistant can still consume jeelink2mqtt's sensors today via manually-configured
[MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/) entities pointed
at `jeelink2mqtt/{name}/state` (JSON `temperature`/`humidity`/`low_battery` fields) and
`jeelink2mqtt/{name}/availability`. See cap-dnw for the full analysis.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
