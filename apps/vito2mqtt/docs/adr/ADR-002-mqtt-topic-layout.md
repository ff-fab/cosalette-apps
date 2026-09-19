# ADR-002: MQTT Topic Layout — Domain-Grouped

## Status

Accepted **Date:** 2026-02-27 | Amended **Date:** 2026-09-19

## Context

The vito2mqtt bridge publishes approximately 100 data points from a Viessmann
Vitodens 200-W boiler. These data points span multiple physical subsystems: outdoor
sensors, domestic hot water, burner, heating circuits, system diagnostics, and more.
The MQTT topic structure must be organized for human discoverability (browsing with
MQTT Explorer), machine consumption (Home Assistant auto-discovery), and future
scalability (additional heating circuits or device types).

A poor topic layout leads to confusing MQTT namespaces, difficult Home Assistant
integration, and awkward payload sizes. Per-domain polling intervals for these topics
are configurable via ADR-005.

## Decision

Use **domain-entity grouping** where each physical subsystem of the boiler gets its own
topic namespace because it provides natural discoverability, maps cleanly to Home
Assistant device/entity concepts, and keeps JSON payloads focused and reasonably sized.

**Topic structure:**

- `vito2mqtt/outdoor/state` — outdoor sensors (temperature)
- `vito2mqtt/hot_water/state` — DHW telemetry (temperatures, flow)
- `vito2mqtt/hot_water/set` — DHW writable parameters (target temp)
- `vito2mqtt/burner/state` — burner telemetry (hours, starts, modulation)
- `vito2mqtt/heating_radiator/state` — M1 heating circuit telemetry
- `vito2mqtt/heating_radiator/set` — M1 writable parameters
- `vito2mqtt/heating_floor/state` — M2 heating circuit (floor) telemetry
- `vito2mqtt/heating_floor/set` — M2 writable parameters
- `vito2mqtt/system/state` — system-level readings (firmware, time)
- `vito2mqtt/system/set` — system writable parameters (time sync)
- `vito2mqtt/diagnosis/state` — error states and status registers

All payloads are JSON objects with English keys.

## Decision Drivers

- Discoverability when browsing topics with MQTT Explorer or similar tools
- Home Assistant MQTT integration compatibility (device → entity mapping)
- Logical grouping that mirrors the physical boiler subsystems
- Scalability to additional heating circuits or future device support
- Reasonable per-topic payload size (not too large, not too fragmented)

## Considered Options

- **Option 1: Domain-entity grouping** — one topic namespace per physical subsystem,
  separate `/state` and `/set` suffixes
- **Option 2: Flat topic per signal** — one topic per data point
  (`vito2mqtt/{device}/outside_temperature`)
- **Option 3: Single aggregated topic** — everything in one JSON blob at
  `vito2mqtt/{device}/state`

## Decision Matrix

| Criterion        | Domain-entity | Flat per signal | Single aggregated |
| ---------------- | ------------- | --------------- | ----------------- |
| Discoverability  | 5             | 3               | 2                 |
| HA integration   | 5             | 4               | 2                 |
| Payload size     | 4             | 5               | 1                 |
| Topic count      | 4             | 1               | 5                 |
| Scalability      | 5             | 3               | 2                 |
| **Total**        | **23**        | **16**          | **12**            |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Topic tree mirrors the physical boiler layout, making it intuitive for users browsing
  MQTT namespaces
- Each domain maps naturally to a Home Assistant device with its entities, simplifying
  auto-discovery configuration
- Separate `/state` and `/set` suffixes follow MQTT conventions and clearly separate
  read-only telemetry from writable commands
- JSON payloads per domain stay focused (10–20 keys each), balancing readability and
  network efficiency
- Adding a new heating circuit (M3) or subsystem requires only adding a new namespace,
  not restructuring existing topics

### Negative

- Subscribers interested in all data must subscribe to multiple topics or use a wildcard
  (`vito2mqtt/#`)
- Domain boundaries require upfront design decisions about which signals belong to which
  group — some signals may not fit neatly
- More topics than a single-aggregated approach means slightly more MQTT overhead
  (retained messages, subscriptions)
- English key names require a translation layer for users expecting manufacturer-specific
  German parameter names

## Amendment (2026-09-19) — Minor

!!! note "Editorial note (2026-09-19)"
    This ADR first listed a `{device_id}` segment after the app prefix, for example `vito2mqtt/{device_id}/outdoor/state`. The app never published that segment. The topic list in the Decision section now shows the real layout: `vito2mqtt/{group}/state` and `vito2mqtt/{group}/set`.

!!! note "Editorial note (2026-09-19)"
    The `device_id` setting is reserved. No topic code reads it, so it does not affect topics. The `{device}` segment in the examples of Option 2 and Option 3 was illustrative and is not part of any layout that the app publishes.

!!! note "Editorial note (2026-09-19)"
    The `device_id` setting does not separate two instances on one broker: both publish to the same topics. To separate them, set a different `VITO2MQTT_MQTT__TOPIC_PREFIX` for each instance. Beads issue cap-ohpx tracks the decision to remove `device_id` or wire it in.
