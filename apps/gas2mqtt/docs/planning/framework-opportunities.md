# Framework Opportunities

Future improvements enabled by the cosalette migration.  These are not planned work
items — they document where the framework leaves room to grow.

## Multi-Sensor Support

cosalette's adapter registry is currently one-adapter-per-port.  If a second gas meter
or a different sensor type is added, the options are:

- **Separate port protocols** — one per sensor model (simplest, works today).
- **Multiplexer adapter** — a single adapter that internally fans out to multiple
  hardware buses.
- **cosalette multi-instance registry** — if the framework adds support in a future
  release.

## Home Assistant Auto-Discovery

Home Assistant's [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
protocol allows devices to self-register by publishing config payloads to
`homeassistant/<component>/<node_id>/config`.

gas2mqtt could publish discovery configs at startup for each device (gas counter,
temperature, magnetometer), eliminating manual HA YAML configuration.  This would be a
natural fit as a lifespan hook or a dedicated cosalette device.

## Metrics / Prometheus Integration

For deployments where MQTT alone is insufficient, a `/metrics` HTTP endpoint could
expose Prometheus-formatted counters (gas ticks, errors, uptime).  This would require
adding an HTTP server — either via cosalette (if it gains HTTP support) or a lightweight
library like `aiohttp`.

## Event-Driven Telemetry

!!! note "Partially realised (cosalette 0.1.2)"
    Temperature and magnetometer have been migrated from `@app.device` to
    `@app.telemetry`.  Temperature uses `OnChange(threshold={"temperature": 0.05})`
    so readings are only published when the EWMA-filtered value changes by more than
    0.05 °C.  Magnetometer is conditionally registered as telemetry when
    `enable_debug_device=True`.

The gas counter still uses `@app.device()` with a manual polling loop because its
publish logic is event-driven (Schmitt trigger state changes), which doesn't fit the
periodic-return-dict model of `@app.telemetry`.  If cosalette adds event-driven or
threshold-based telemetry variants, the gas counter could become simpler — publishing
only when the trigger fires rather than polling on a fixed interval.

## Calibration Commands

The Schmitt trigger thresholds (`trigger_level`, `trigger_hysteresis`) are currently
static settings.  An MQTT command interface could allow runtime re-calibration:

```json
{"trigger_level": -4800, "trigger_hysteresis": 600}
```

This would be a natural fit for `@app.command("gas_counter")` with validation and
state publication of the active thresholds.

## Structured Logging

cosalette configures Python logging.  A future step could add structured JSON logging
(via `python-json-logger` or similar) for better integration with log aggregators like
Loki or ELK.
