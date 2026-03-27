# Framework Improvement Proposals

These proposals capture framework gaps identified during development of caldates2mqtt
and sibling cosalette apps. Each documents a real limitation encountered in production
code, the workaround used, and a proposed framework improvement.

---

## 1. Lazy Device Registration from Settings

**Context:** caldates2mqtt registers one device per configured calendar using
`app.add_device()` in a loop at module level. This requires eagerly constructing settings
before `app.run()` to iterate over the calendar list.

**Current behavior:** `_settings = CalDates2MqttSettings()` is called at module level in
`main.py`. If required environment variables (like `CALDATES2MQTT_CALENDARS`) are missing,
the import crashes --- even for `--help` and `--version`.

**Workaround:** Accept the crash. Document that `CALDATES2MQTT_CALENDARS` must be set
even to see help text.

**Proposed improvement:** A settings-driven registration hook:

```python
@app.on_configure
def register_devices(settings: CalDates2MqttSettings) -> None:
    for cal in settings.calendars:
        app.add_device(cal.key, make_calendar_handler(cal))
```

**Impact:** This is the single most impactful framework gap for caldates2mqtt. It affects
any app that dynamically registers devices from settings.

**Apps affected:** caldates2mqtt (multi-calendar), velux2mqtt (multi-cover),
airthings2mqtt (potential multi-sensor).

---

## 2. Configurable Retry/Backoff on @app.device

**Context:** CalDAV servers can be transiently unavailable (maintenance windows, network
glitches). The `@app.device()` loop handles errors by logging and continuing, but there
is no built-in retry mechanism with backoff.

**Current behavior:** When `read_events()` raises an error (e.g. `CalDavConnectionError`),
the framework publishes to the error topic and the device loop continues to the next
`ctx.sleep()`. The next read attempt waits for the full poll interval (default 2 hours).

**Workaround:** Accept the 2-hour gap. Calendar data is not time-critical enough to
warrant custom retry logic in the device handler.

**Proposed improvement:** Configurable retry/backoff:

```python
@app.telemetry(
    "calendar",
    interval=7200,
    retry=3,
    backoff="exponential",
    retry_on=(CalDavConnectionError, CalDavTimeoutError),
)
```

**Impact:** Eliminates multi-hour data gaps from transient CalDAV server failures.

**Apps affected:** caldates2mqtt (CalDAV flakiness), airthings2mqtt (BLE flakiness),
vito2mqtt (serial timeouts).

---

## 3. Scheduled/Cron-Like Device Archetype

**Context:** caldates2mqtt polls every 2 hours, but calendar data is inherently
date-aligned. Events change on day boundaries (new day = new "upcoming" window), not at
fixed intervals. A cron-like schedule ("read at 06:00 and 18:00") would be more natural
than a fixed 7200-second interval.

**Current behavior:** `@app.device` uses `ctx.sleep(seconds)` for fixed-interval polling.
The 2-hour default means the event list may be stale for up to 2 hours after midnight
when the date window shifts.

**Workaround:** Use the fixed 2-hour interval, which is good enough but semantically
wrong --- it polls 12 times per day when 2 well-timed polls would suffice.

**Proposed improvement:**

```python
@app.telemetry("calendar", schedule="0 6,18 * * *")
# or for @app.device:
await ctx.sleep_until(time(6, 0))
```

**Impact:** Any app where data is time-of-day aligned rather than interval-based.
Calendar apps, utility meter daily summaries, solar production reports, weather forecasts.

**Apps affected:** caldates2mqtt (calendar dates are day-aligned). No existing app has
documented this need.

---

## 4. Command-Loop Bridge

**Context:** caldates2mqtt uses `@ctx.on_command` to register a re-read command handler
inside the `@app.device()` loop. The command handler runs as an independent callback,
which works for caldates2mqtt's simple use case (just call `_read_and_publish()`) but does
not integrate with the polling loop.

**Current behavior:** `@ctx.on_command` fires as an asyncio callback. No built-in queue
or message-passing mechanism exists between the command handler and the polling loop.

**Workaround:** The command handler calls `_read_and_publish()` directly, which is safe
because it only does a stateless read-and-publish. More complex scenarios (e.g. updating
loop state from a command) would require manual `asyncio.Queue` plumbing.

**Proposed improvement:** Built-in command channel in `DeviceContext`:

```python
async def device(ctx: DeviceContext) -> None:
    async for cmd in ctx.commands():
        await handle(cmd)
```

**Impact:** Would standardise the command-to-loop communication pattern.

**Apps affected:** caldates2mqtt, velux2mqtt, vito2mqtt --- all use `@ctx.on_command`
with varying degrees of loop integration.
