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

The gas counter currently uses `@app.device()` with a manual polling loop.  If cosalette
adds event-driven or threshold-based `@app.telemetry()` variants, the gas counter could
become simpler — publishing only when the Schmitt trigger fires rather than polling on a
fixed interval.

Temperature reporting could also benefit from a "publish on change" mode where readings
are only emitted when the EWMA-filtered value moves beyond a configurable delta.

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
