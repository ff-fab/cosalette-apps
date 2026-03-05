# ADR-002: Sensor ID Management Strategy

## Status

Accepted **Date:** 2026-03-04

## Context

LaCrosse temperature/humidity sensors transmit with ephemeral numeric IDs that change on
every battery replacement. Downstream consumers need stable MQTT topics per sensor —
subscribing to `sensors/kitchen/temperature` rather than chasing
`sensors/42/temperature` which changes unpredictably.

The application must therefore maintain a stable mapping from transient sensor IDs to
logical sensor names (representing physical locations). This mapping must handle:

- **Battery replacements** — a sensor's numeric ID changes; the logical name must
  persist
- **Multi-sensor failures** — when multiple sensors lose power simultaneously,
  disambiguation becomes ambiguous
- **Neighbour interference** — unknown IDs from nearby LaCrosse sensors should not
  pollute the mapping
- **Debugging** — operators need visibility into raw readings when troubleshooting

## Decision

Use a **hybrid approach**: app-managed named sensors with auto-adopt for unambiguous
battery swaps, plus a raw diagnostic channel for debugging and manual disambiguation.

## Decision Drivers

- Operational simplicity for downstream consumers (stable topics, no rules needed)
- Battery-swap resilience (automatic re-mapping without operator intervention)
- Multi-sensor failure recovery (safe fallback when auto-adopt is ambiguous)
- Debuggability (raw data visible for troubleshooting)
- Separation of concerns (app handles sensor identity, consumer handles display)

## Considered Options

1. **App-side auto-mapping only** — the app manages the full ID→name mapping
   internally. Unknown IDs are auto-assigned when exactly one configured sensor
   is stale (single-stale condition). Publishes per-sensor named topics.

2. **Pass-through with metadata** — publish raw sensor IDs to MQTT. Let downstream
   consumers handle the name mapping via their own automation rules. App adds
   staleness metadata.

3. **Hybrid: named sensors + raw diagnostic channel** — same as Option 1 for normal
   operation, but additionally publishes all raw readings to a diagnostic topic for
   debugging multi-sensor failures and manual disambiguation.

## Decision Matrix

| Criterion                      | Auto-mapping only | Pass-through | Hybrid |
| ------------------------------ | ----------------- | ------------ | ------ |
| Downstream simplicity          | 5                 | 1            | 5      |
| Battery-swap resilience        | 4                 | 2            | 4      |
| Multi-sensor failure recovery  | 2                 | 3            | 4      |
| Debuggability                  | 2                 | 4            | 5      |
| Separation of concerns         | 4                 | 2            | 4      |
| Implementation complexity      | 4                 | 5            | 3      |
| **Total**                      | **21**            | **17**       | **25** |

_Scale: 1 (poor) to 5 (excellent)_

## Auto-Adopt Algorithm

The core logic for handling an unknown sensor ID:

1. **Exactly one configured sensor is stale** (no readings for configurable timeout,
   default 10 minutes) → auto-assign the new ID to that stale sensor. Log and publish
   the mapping change.

2. **Zero sensors are stale** → track the ID as "unmapped". This is likely a
   neighbour's sensor or RF interference. Do not create a mapping.

3. **Multiple sensors are stale** → do NOT auto-assign (ambiguous). Log a warning.
   The operator must disambiguate manually using the diagnostic channel or an MQTT
   command.

All mapping changes (auto-adopt and manual) are logged and published to MQTT for
auditability.

## Consequences

### Positive

- Downstream consumers subscribe to stable, human-readable topics — no client-side
  mapping logic needed
- Single battery swap is handled fully automatically with zero operator intervention
- Raw diagnostic channel provides full visibility for troubleshooting without polluting
  the primary sensor topics
- Ambiguous situations (multi-sensor failure) fail safe — no incorrect auto-assignment
- Manual override via MQTT command provides escape hatch for edge cases

### Negative

- Auto-adopt logic adds complexity to the sensor registry
- Multi-sensor simultaneous battery failure requires manual intervention
- Diagnostic channel increases MQTT traffic (mitigated: it's a single topic, consumers
  opt in)
- Operators must understand the auto-adopt algorithm to troubleshoot mapping issues

_2026-03-04_
