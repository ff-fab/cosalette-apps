# Framework Improvement Proposals

These proposals capture framework gaps identified during development of airthings2mqtt
and sibling cosalette apps. Each documents a real limitation encountered in production
code, the workaround used, and a proposed framework improvement.

---

## 1. Event-Driven Telemetry with Configurable Retry/Backoff

**Context:** airthings2mqtt polls a BLE sensor at a fixed interval. BLE connections are
inherently unreliable --- interference, range limits, and adapter resets cause transient
failures. The `@app.telemetry` decorator has no built-in retry or backoff mechanism.

**Current behavior:** If `reader.read()` raises a BLE error, the framework's error
handling catches it and waits for the next polling cycle. A single transient failure
means no data for another 25 minutes (the default poll interval).

**Workaround:** The adapter maps low-level exceptions to domain errors
(`BleConnectionError`, `BleTimeoutError`, `BleReadError`) which the framework logs. No
retry is attempted --- the next reading waits for the full interval.

**Proposed improvement:** Configurable retry/backoff on `@app.telemetry`:

```python
@app.telemetry(
    "airthings",
    interval=_poll_interval,
    retry=3,
    backoff="exponential",  # 2s, 4s, 8s
    retry_on=(BleConnectionError, BleTimeoutError),
)
async def _telemetry(reader: AirthingsReaderPort, settings: Airthings2MqttSettings) -> dict[str, object]:
    reading = await reader.read(settings.device_mac)
    return {...}
```

**Impact:** Eliminates 25-minute data gaps from transient BLE failures. Standardises
retry logic across all telemetry-based apps instead of each app implementing its own.

**Apps affected:** airthings2mqtt (BLE flakiness), vito2mqtt (serial timeouts), gas2mqtt
(meter read failures).

---

## 2. Multi-Device Registration from Settings

**Context:** Users with multiple Airthings sensors need one telemetry device per sensor.
Currently, `app.add_device()` must be called before `app.run()`, requiring eager settings
construction at module level.

**Current behavior:** airthings2mqtt registers a single device at module level. Adding a
second sensor requires environment variable changes and a second container instance.

**Workaround:** The getting-started guide documents a multi-container pattern --- one
`docker-compose` service per sensor with different `DEVICE_MAC` and `DEVICE_NAME`
environment variables.

**Proposed improvement:** A settings-driven registration hook (same as velux2mqtt
proposal #4):

```python
@app.on_configure
def register_devices(settings: Airthings2MqttSettings) -> None:
    for sensor in settings.sensors:
        app.add_device(sensor.name, make_handler(sensor))
```

**Impact:** Single container instance for multiple sensors. Eliminates duplicate
container overhead and simplifies configuration.

**Apps affected:** airthings2mqtt (multi-sensor), velux2mqtt (multi-cover), gas2mqtt
(multi-meter).

---

## 3. Adapter Health Check / Readiness Probe

**Context:** BLE adapters can enter a wedged state (BlueZ daemon crash, adapter hardware
reset) where connections fail indefinitely. There is no framework mechanism to detect
adapter health or signal unreadiness.

**Current behavior:** `@app.telemetry` continues calling the adapter on schedule. Each
call fails, logs an error, and waits for the next cycle. The availability topic stays
`online` even when the adapter is non-functional.

**Workaround:** None. The operator must notice repeated errors in logs and manually
restart the container or Bluetooth service.

**Proposed improvement:** Adapter-level health check with availability integration:

```python
class BleakAirthingsReader:
    async def health_check(self) -> bool:
        """Return True if the BLE adapter is responsive."""
        ...

# Framework auto-calls health_check() and sets availability accordingly
```

**Impact:** Accurate availability reporting to Home Assistant. Enables alerting on
adapter failures without log parsing.

**Apps affected:** airthings2mqtt (BLE adapter), velux2mqtt (GPIO), jeelink2mqtt (serial
port).

---

## 4. Lifespan-Yielded Injectable State

**Context:** Same gap as documented in velux2mqtt proposal #3. If airthings2mqtt needed
shared state across telemetry cycles (e.g. a connection pool or cached calibration data),
there is no DI-friendly way to create it in lifespan and inject it into handlers.

**Current behavior:** `AppContext` in lifespan has `.settings` and `.adapter()` but no
way to yield state for injection.

**Workaround:** Not yet needed for airthings2mqtt (single stateless telemetry call), but
the limitation would surface if connection pooling or calibration caching were added.

**Proposed improvement:** Same as velux2mqtt proposal #3 --- lifespan yields a value
registered in DI (FastAPI pattern).

**Impact:** Enables connection pooling, calibration caching, and shared sensor state
without module globals.

**Apps affected:** jeelink2mqtt (SharedState singleton), potentially airthings2mqtt and
vito2mqtt.

---

## 5. Command->Loop Bridge

**Context:** Same as velux2mqtt proposal #6. If airthings2mqtt added command support
(e.g. force-read, recalibrate), there is no standard pattern for bridging
`@ctx.on_command` callbacks into the telemetry loop.

**Current behavior:** `@ctx.on_command` fires as an asyncio callback. No built-in queue
or message-passing exists.

**Workaround:** Not yet needed for airthings2mqtt (read-only telemetry). Three different
patterns exist across sibling apps.

**Proposed improvement:** Same as velux2mqtt proposal #6 --- built-in command channel in
`DeviceContext`.

**Impact:** Would standardise the pattern before airthings2mqtt needs it.

**Apps affected:** All existing apps.
