# jeelink2mqtt

A smart home app to read in values of Jeelink temperature and humidity sensors.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Not applicable.** This app does not emit Home Assistant MQTT discovery payloads, and
its `docs/schema.yaml` carries no `x-cosalette-consumer` annotations (running
`task jeelink2mqtt:schema:ha-discovery` yields an empty payload list `[]`).

jeelink2mqtt is a **STREAM**-archetype app: sensors are configured by logical name
(`settings.sensors`), but the ephemeral LaCrosse ID behind each name is resolved at
runtime via auto-adopt (ADR-002), and readings are published to per-sensor topics
(`{name}/state`, `{name}/availability`) rather than to static, schema-annotated
properties. cosalette's HA discovery generator (`cosalette schema ha-discovery`) works
by walking the static AsyncAPI schema registry built from decorator introspection —
there is no per-sensor entry in that registry to annotate, so the static pipeline used
by airthings2mqtt, gas2mqtt, velux2mqtt, vito2mqtt, and wallpanel-control does not apply
here.

A **runtime** discovery mechanism (publishing `homeassistant/.../config` messages as
each sensor first appears) was also evaluated and rejected:
`cosalette.DeviceContext.publish()` is deliberately scoped to the app's own topic prefix
(`jeelink2mqtt/...`) — there is no public API for a device handler to publish to the
shared `homeassistant/` discovery namespace used by other integrations on the same
broker. Reaching into the framework's internal MQTT client to bypass that scoping would
break the ports-and-adapters boundary this app otherwise holds to strictly
(jeelink2mqtt's [ADR-001](docs/adr/ADR-001-application-framework.md), which chose
cosalette specifically for its hexagonal architecture), and no other app in this repo
does runtime discovery publishing — every enriched app relies exclusively on the static,
build-time `schema:ha-discovery` pipeline.

Home Assistant can still consume jeelink2mqtt's sensors today via manually-configured
[MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/) entities pointed
at `jeelink2mqtt/{name}/state` (JSON `temperature`/`humidity`/`low_battery` fields) and
`jeelink2mqtt/{name}/availability`. Automating that would require either an upstream
cosalette API for publishing outside an app's own topic prefix, or a static per-sensor
schema registration mechanism — both are future enhancements, not implemented here. See
cap-dnw for the full analysis.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
