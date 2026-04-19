# ADR-001: Migrate to cosalette Framework

## Status

Accepted **Date:** 2026-03-27

## Context

The caldates2mqtt application reads upcoming all-day events from CalDAV calendars
(Nextcloud) and publishes them as JSON to MQTT for consumption by Home Assistant and
other smart home systems. The legacy implementation was a pull-based REST endpoint in
jl4services --- a monolithic service that polled calendars and served results over HTTP.

Key concerns that drove the migration:

- **Push-based architecture** --- the legacy REST endpoint required consumers to poll for
  data. An MQTT-native approach pushes updates to subscribers, eliminating polling
  overhead and enabling real-time notifications.
- **Independent lifecycle** --- bundling calendar reading inside jl4services coupled
  deployment with unrelated services. A standalone app can be deployed, updated, and
  restarted independently.
- **Multi-calendar support** --- the legacy service handled a single calendar. The new
  design registers one device per configured calendar, supporting any number of calendars
  from a single instance.
- **Operational visibility** --- the legacy service had no health reporting. MQTT-native
  heartbeats, per-device availability, and LWT are essential for detecting silent failures
  in unattended deployments.
- **Command support** --- consumers need the ability to trigger immediate re-reads (e.g.
  after adding a calendar event). MQTT commands are a natural fit.

## Decision

Build caldates2mqtt on the **cosalette** IoT-to-MQTT framework (v0.1.8+).

cosalette provides:

- `@app.device()` for full-lifecycle coroutines with periodic polling and command handling
- `app.add_device()` for dynamic registration of multiple devices from settings
- Automatic MQTT connection management with reconnect
- Built-in health reporting: heartbeats, per-device availability, LWT
- Pydantic-based settings with env / `.env` / CLI layering
- Dependency injection via type annotations
- Adapter registration with dry-run alternatives

### Key Design Choices

- **`app.add_telemetry()` with `triggerable=True`**: caldates2mqtt uses
  `app.add_telemetry()` for dynamic registration of one telemetry device per configured
  calendar. `TriggerPayload` provides on-demand re-read via MQTT with optional parameter
  overrides. Supersedes the original `@app.device()` choice (see Addendum).
- **Dynamic registration from settings**: calendars are configured as a JSON list in
  environment variables. `app.add_telemetry()` is called in a loop from `@app.on_configure`,
  one device per calendar.
- **Stateless CalDAV adapter**: each `read_events()` call creates a fresh `DAVClient`.
  CalDAV connections are infrequent (every 2 hours) and short-lived, making connection
  pooling unnecessary.
- **Thread executor for synchronous library**: the `caldav` library is synchronous.
  `asyncio.to_thread()` bridges it into the async event loop without blocking.

## Decision Drivers

- **Error isolation** --- CalDAV servers can be transiently unavailable (network issues,
  maintenance windows). The `@app.device()` coroutine handles errors in its loop, while
  the framework provides automatic error publishing and deduplication.
- **Testability** --- the Ports & Adapters pattern lets us swap the real CalDAV adapter
  for a `FakeCalDavReader` in tests, enabling full coverage without a CalDAV server.
- **Shutdown awareness** --- `ctx.sleep()` returns early on SIGTERM/SIGINT, enabling
  graceful shutdown even during 2-hour polling intervals.
- **Configuration** --- Pydantic settings with the `CALDATES2MQTT_` prefix support
  Docker-native `.env` files. The `calendars` field accepts a JSON list, enabling
  flexible multi-calendar configuration.
- **Operational visibility** --- heartbeats and LWT are free from cosalette, essential
  for unattended deployments.

## Considered Options

1. **cosalette framework** --- purpose-built for IoT-to-MQTT bridges.
2. **Standalone asyncio + aiomqtt** --- custom async loop without a framework.
3. **Keep in jl4services** --- add MQTT publishing to the existing monolith.

## Decision Matrix

| Criterion              | cosalette | Standalone | jl4services |
| ---------------------- | --------- | ---------- | ----------- |
| Multi-calendar support | 5         | 4          | 3           |
| Testability            | 5         | 3          | 2           |
| Operational visibility | 5         | 2          | 2           |
| Command support        | 5         | 4          | 1           |
| Migration effort       | 4         | 4          | 5           |
| Deployment flexibility | 5         | 5          | 2           |
| Maintenance burden     | 5         | 3          | 2           |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- **Ports-and-adapters architecture** --- domain types (`CalendarEvent`, `CalDavPort`)
  have zero I/O dependencies. The CalDAV adapter is a thin wrapper that translates library
  calls to domain types.
- **Comprehensive test suite** --- unit tests cover the device handler, adapter error
  translation, settings validation, and command dispatch without a CalDAV server.
- **Multi-calendar from config** --- `app.add_telemetry()` in `@app.on_configure` creates
  one telemetry device per configured calendar, all managed by a single process.
- **On-demand re-read** --- `TriggerPayload` enables consumers to trigger immediate
  reads with optional parameter overrides via MQTT on `{prefix}/{device}/set`.
- **Automatic health reporting** --- heartbeats, per-device availability, and LWT come
  free from cosalette.
- **Docker-ready** --- no special hardware access required. Simple `docker compose up`
  deployment with only network access to CalDAV and MQTT.

### Negative

- **Framework dependency** --- the application depends on cosalette's lifecycle and
  conventions. API changes in cosalette require migration work.
- **Python 3.14+ requirement** --- cosalette requires Python 3.14+, limiting deployment
  to systems with recent Python.
- **~~Eager settings construction~~** --- **Fixed.** Dynamic device registration now
  uses `@app.on_configure`, which defers settings access until after CLI parsing.
  `--help` and `--version` work without env vars.

_2026-03-27_

## Addendum: cosalette 0.3.3 — Triggerable Telemetry

_2026-04-19_

cosalette 0.3.3 introduces `triggerable=True` on `@app.telemetry`, which allows a
telemetry device to respond to inbound MQTT messages on `{prefix}/{device}/set` in
addition to its normal polling interval. The `TriggerPayload` injectable lets handlers
distinguish triggered from scheduled runs and access parsed payload data.

This partially invalidates the original rationale for choosing `@app.device()` over
`@app.telemetry()`. The key decision driver — "caldates2mqtt needs on-demand re-read
via MQTT command, and `@app.telemetry()` only supports periodic return-dict semantics
with no command handling" — no longer holds. Triggerable telemetry provides exactly the
on-demand re-read capability that drove the `@app.device()` choice, while the framework
handles retry, scheduling, and publishing automatically.

**Completed.** Calendar devices were converted to `app.add_telemetry()` with
`triggerable=True`, registered dynamically via `@app.on_configure` (device count is
determined by settings). A factory function `make_calendar_handler()` produces each
handler. `TriggerPayload` replaced the old `@ctx.on_command` pattern for on-demand
re-reads with optional parameter overrides. The `devices/` directory was removed — all
code now lives in a single `main.py`.
