# caldates2mqtt

CalDAV calendar dates to MQTT bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

## Home Assistant Discovery

**Still not functional — one of two original blockers is now resolved.** Running
`task caldates2mqtt:schema:ha-discovery` still yields an empty payload list `[]`.

`docs/schema.yaml` carries a typed `state_model` (`CalendarState` in `main.py`, wired
via `state_model=` on `@app.telemetry`) so the channel is no longer a bare
`additionalProperties: true` object, and its nested `CalendarEvent` fields (`title`,
`date`) carry `cosalette.schema.consumer(...)` annotations ready for when discovery
becomes possible. Two independent things originally blocked a working entity:

1. **Callable `name=` collapse — RESOLVED.** `app.telemetry` is registered with a
   callable `name=` (`_calendar_map`, keyed off user-configured `settings.calendars`),
   so a plain `cosalette schema init`/`check` would collapse every real per-calendar
   device into one channel named after this handler's qualname (`calendar`) — the same
   issue that produced a phantom entity for velux2mqtt (see that app's README). Here,
   `task caldates2mqtt:schema:generate` now runs
   `cosalette schema dump --resolve-settings` (ADR-051) against the checked-in
   `.env.schema` profile, expanding the NameSpec into real per-calendar channels
   (`birthdayState`, `garbageState`, ...) — see `docs/schema.yaml` and cap-0cg.
   `cosalette schema check` (the CI gate) now validates this app too: cosalette 0.6.0
   extended `--resolve-settings`/`--env-file` to `schema check` (previously dump-only,
   cap-wv9 part b), so the task runs it against the same `.env.schema` profile.
2. **Nested list payload — still blocked.** The `calendar` handler publishes
   `{"events": [{"title": ..., "date": ...}, ...]}`. cosalette's HA/OpenHAB generators
   only walk a channel's top-level properties, never items inside a nested list — so the
   per-event `consumer()` annotations remain inert regardless of (1), and Home Assistant
   has no standard `device_class` for a calendar event list even if they weren't. This
   is a separate, still-open upstream limitation.

This model is prepared so caldates2mqtt is ready the moment list/array payload support
lands upstream — no further modeling work needed here.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
