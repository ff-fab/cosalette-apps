# Framework Enhancement Request: `triggerable=True` on `@app.telemetry`

**Status:** Proposal
**Origin:** caldates2mqtt v0.3.2 migration
**Target:** cosalette framework

---

## Background

During the caldates2mqtt migration to `@app.telemetry`, the question arose whether
calendar devices should support a "refresh now" command — a way for users or automations
to trigger an immediate re-read without waiting for the next poll interval.

The current `@app.telemetry` model is purely schedule-driven. There is no mechanism
to externally trigger an immediate execution. The only alternative is `@app.device` +
`ctx.commands()`, which requires the app to implement the entire polling loop manually.

---

## Problem

App developers who want **schedule-driven polling** (the common case) plus
**on-demand refresh** (an occasional convenience) have two unappealing options:

1. **`@app.telemetry` only** — clean, declarative, but no user-triggered refresh.
2. **`@app.device` + `ctx.commands()`** — full control, but requires a manual async
   loop, manual retry/backoff, manual state publish, manual initial read. All the
   framework-level conveniences are lost.

There is no "telemetry with optional trigger" middle ground.

---

## Proposed Solution

Add a `triggerable=True` parameter to `@app.telemetry` (and `app.add_telemetry()`).

When enabled, the framework:

1. Subscribes to a well-known command topic for the device:
   `{prefix}/{device_name}/set`
2. When any MQTT message arrives on that topic, runs the telemetry function
   immediately, bypassing the normal schedule.
3. After the triggered run, the schedule resets (or continues unchanged — either
   is acceptable; resetting seems more useful).
4. The payload of the trigger message is **ignored** (no parameter injection).
   The purpose is "run now", not "run with these parameters".

### API sketch

```python
# Decorator form
@app.telemetry("garbage", interval=3600, triggerable=True)
async def read_calendar(reader: CalDavPort) -> dict[str, object]:
    ...

# Imperative form (inside @app.on_configure)
app.add_telemetry(
    "garbage",
    read_calendar,
    interval=3600,
    triggerable=True,
)
```

### User-facing behavior

```
# Home Assistant button, shell, or any MQTT client:
mosquitto_pub -t "caldates2mqtt/garbage/set" -m ""

# Framework immediately runs read_calendar() without waiting for next poll.
```

---

## Motivation

### caldates2mqtt use case

Calendar data (bin collection dates, public holidays) changes infrequently. A 1–2 hour
poll interval is perfectly adequate for normal operation. But users may occasionally
want to force a refresh — for example, after fixing a CalDAV credential, after a
network outage, or just to confirm the connection is working.

With `triggerable=True`, this "refresh now" capability is available out of the box
with a single parameter. Without it, the app must drop back to `@app.device` and
reimplement everything the framework already provides.

### General applicability

The pattern applies to any sensor that is slow to poll but occasionally needs
on-demand reads:

- Weather APIs (rate-limited, hourly poll, "what's the weather right now?")
- Gas meter readings (daily poll, "read now" after coming home)
- Air quality sensors (15-minute poll, "check now" before opening windows)
- Any HTTP-scraped data source

---

## What would NOT be supported

- **Payload-as-parameters:** The trigger payload is ignored. If parameter injection
  is needed, that is a separate, more complex feature (see note below).
- **Rate-limiting triggers:** No debounce or minimum trigger interval is proposed.
  The framework could add this later if needed.
- **Topic customization:** The topic `{prefix}/{device}/set` follows the existing
  cosalette convention for device commands and should not be configurable.

> **Note on parameter injection:** An earlier version of caldates2mqtt used
> `ctx.commands()` to accept `entries` and `days` overrides via the command payload.
> This was dropped because the use case was marginal and the complexity was high.
> If parameter injection is ever needed, it should be a separate, opt-in feature
> (e.g., `injectable_params=True`), distinct from `triggerable=True`.

---

## Backward Compatibility

- Default: `triggerable=False` — no behavior change for existing apps.
- No subscription is created unless explicitly enabled.
- Fully orthogonal to `retry=`, `backoff=`, `schedule=`, and other telemetry parameters.

---

## Implementation Notes (for framework author)

Internally, this could be implemented as:

1. During telemetry device startup, if `triggerable=True`:
   - Subscribe to `{prefix}/{device_name}/set`
   - On message: cancel the current sleep/schedule, run the telemetry function immediately
2. The existing retry/backoff/error machinery applies to triggered runs identically
   to scheduled runs — no special casing needed.
3. The subscription is torn down with the device on shutdown.

This is structurally similar to how `ctx.commands()` works inside `@app.device`, but
abstracted at the framework level so app developers do not need to manage it.

---

## Related

- caldates2mqtt PR that prompted this request: `feat/caldates-v032-migration`
- cosalette `ctx.commands()` (existing, `@app.device`-only): the manual equivalent
- Follow-up task in cosalette-apps: apply `triggerable=True` to caldates2mqtt once
  the feature ships
