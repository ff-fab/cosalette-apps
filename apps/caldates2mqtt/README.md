# caldates2mqtt

CalDAV calendar dates to MQTT bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-blue)](https://www.python.org/)

Built on the [cosalette](https://github.com/ff-fab/cosalette) IoT framework, currently
on the 0.9.5 release.

## Home Assistant Discovery

**Working — one event-count sensor per calendar.** Running
`task caldates2mqtt:schema:ha-discovery` yields one `sensor` per configured calendar
(`birthday_events`, `garbage_events`) plus the ADR-058 app bridge, and exits 0.

`docs/schema.yaml` carries a typed `state_model` (`CalendarState` in `main.py`, wired
via `state_model=` on `@app.telemetry`) so the channel is not a bare
`additionalProperties: true` object. Two independent things originally blocked a working
entity:

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
2. **Nested list payload — RESOLVED for the count, still open for the list.** The
   `calendar` handler publishes `{"events": [{"title": ..., "date": ...}, ...]}`.
   cosalette's generators only walk a channel's top-level properties, never items inside
   a nested list, so the per-event `consumer()` annotations on `CalendarEvent` remain
   inert and still warn on stderr. The supported answer is a _channel-level_
   `ha_entities()` composite (cosalette ADR-057), which `CalendarState` now carries: it
   derives one entity from the whole payload rather than from a single property, so
   `{{ value_json.events | length }}` becomes an event-count sensor with
   `state_class: measurement` for long-term statistics.

   The event **list** itself is still not carried to Home Assistant. Doing so needs
   `json_attributes_topic`, which cosalette 0.9.4 neither emits nor can resolve per
   instance from a model-level spec shared by every calendar. That is the remaining
   upstream limitation (cap-wxg).

Note that openHAB is unaffected by the composite: its generator ignores `ha_entities`,
so `task caldates2mqtt:schema:openhab` still exits 1, exactly as it did before.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, common commands, project
structure, and development guidelines.

## License

MIT License. See [LICENSE](LICENSE) for details.
