# caldates2mqtt

CalDAV calendar dates to MQTT bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Not yet functional — prepared, not blocked on this app.** Running
`task caldates2mqtt:schema:ha-discovery` still yields an empty payload list `[]`.

`docs/schema.yaml` now carries a typed `state_model` (`CalendarState` in `main.py`,
wired via `state_model=` on `@app.telemetry`) so the channel is no longer a bare
`additionalProperties: true` object, and its nested `CalendarEvent` fields (`title`,
`date`) carry `cosalette.schema.consumer(...)` annotations ready for when discovery
becomes possible. Two independent things still block a working entity today:

1. **Nested list payload.** The `calendar` handler publishes
   `{"events": [{"title": ..., "date": ...}, ...]}`. cosalette's HA/OpenHAB generators
   only walk a channel's top-level properties, never items inside a nested list — so the
   per-event `consumer()` annotations are currently inert, and Home Assistant has no
   standard `device_class` for a calendar event list even if they weren't.
2. **Callable `name=` collapse.** `app.telemetry` is registered with a callable `name=`
   (`_calendar_map`, keyed off user-configured `settings.calendars`), so cosalette's
   static schema pipeline collapses every real per-calendar device into one channel
   named after this handler's qualname (`calendar`) — the same issue that produced a
   phantom entity for velux2mqtt (see that app's README) before its consumer annotation
   was removed as a fix. caldates2mqtt never shipped that bug because its channel had no
   consumer annotations to begin with.

Both are prerequisites for the same upstream settings-aware schema pipeline. This model
is prepared so caldates2mqtt is ready the moment that pipeline (and list/array payload
support) lands — no further modeling work needed here.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
