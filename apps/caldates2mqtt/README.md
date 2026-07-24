# caldates2mqtt

CalDAV calendar dates to MQTT bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Not applicable.** This app does not emit Home Assistant MQTT discovery payloads, and
its `docs/schema.yaml` carries no `x-cosalette-consumer` annotations (running
`task caldates2mqtt:schema:ha-discovery` yields an empty payload list `[]`).

The `calendar` telemetry handler publishes an event-list payload — a `dict[str, object]`
of the shape `{"events": [{"title": ..., "date": ...}, ...]}` — with one MQTT topic per
configured calendar (the `_calendar_map` name pattern). Home Assistant has no standard
`device_class` for a calendar event list, and the payload is a nested structure rather
than a scalar HA can map directly to a `sensor` / `binary_sensor` entity. Surfacing it
would require an app-specific value template (for example "days until next event" or
"event active today") that has no standard discovery mapping.

This is a future enhancement, not a gap: it can be revisited once the discovery library
supports event-list payloads. See
[`docs/planning/cap-3bz-ha-discovery-schema-enrichment.md`](../../docs/planning/cap-3bz-ha-discovery-schema-enrichment.md)
for the full analysis.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
