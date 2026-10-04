---
status: Accepted
date: 2026-10-04
impact: moderate
tags: [telemetry, persistence, mqtt]
---

# ADR-004: Withhold radon placeholders after a sensor reset and publish measurement_state

## Status

Accepted **Date:** 2026-10-04

## Context

An Airthings Wave that loses power, for example during a battery change, forgets its radon averages. Until it has computed new ones it reports `0` for both the 24 h and the long-term average (LTA). The radon fields are 16-bit integers in the BLE frame, so a placeholder `0` cannot be told apart from a measured `0` by the frame alone.

In the 2026-10-01/02 incident reported by an early adopter, the LTA went from 113 Bq/m³ to `0/0` for several polls, then to a 24 h value of 95 with an LTA of 4. airthings2mqtt published all of these readings as measurements. The `0` values reached Home Assistant and the adopter's long-term database as genuine readings and skewed averages and alerts. The fresh LTA of 4 then looked like a dramatic improvement although it covered only one day.

The app sees one reading per poll (default 25 min) and has no other signal of a power cycle. cosalette 0.11 provides a per-device `DeviceStore` that survives restarts, which can hold the previous reading.

## Decision

Use a pure reset tracker (`airthings2mqtt.lifecycle.track`) with the previous LTA persisted in the telemetry handler's `DeviceStore` to detect a sensor reset, publish both radon averages as `null` while the sensor reports the `0/0` placeholder, and add `measurement_state` (`warming_up` / `provisional` / `ok`) and `sensor_reset_at` to the state payload, because this removes the false zeros at the source while keeping every consumer informed with retained state and no new topics.

A reading is a reset when it is the `0/0` placeholder and the previous LTA was not already `0` (an empty store counts as a reset: a sensor fresh from a battery change), or when the LTA falls below 25 % of a previous LTA of at least 20 Bq/m³. After a reset the payload is `provisional` for `lta_settle_days` (default 30, `0` disables the phase) and `ok` afterwards. The LTA that the reset wiped and a reset counter stay in the store for diagnostics.

## Decision Drivers

- A radon `0` must never be published as a measurement when it is a placeholder
- Consumers (Home Assistant, openHAB, databases) must be able to tell a fresh LTA from a settled one
- Detection must survive an app restart in the middle of a warm-up
- No new MQTT topics, no new runtime dependencies, logic testable without BLE or MQTT
- Keep ADR-003: the app does not act on the hardware, it only interprets readings

## Considered Options

### Option 1: Persisted reset tracker with measurement_state (chosen)

A pure function classifies each reading against the previous LTA kept in the DeviceStore, nulls the radon placeholders, and adds measurement_state and sensor_reset_at to the retained state payload.

- *Advantages:* False zeros never reach any consumer; State survives restarts through the framework store; SaveOnChange writes only when the tracker changes; Consumers get explicit, retained context; HA shows null as unknown without extra templating
- *Disadvantages:* Heuristic: an indoor LTA of exactly 0 Bq/m³ would be withheld; Two more fields and HA entities on the state payload

### Option 2: Stateless zero filter

Publish every radon value of 0 as null, with no memory of earlier readings.

- *Advantages:* Trivial, no persistence; Removes the false zeros
- *Disadvantages:* Cannot recognise the collapsed LTA (113 -> 4) as fresh; Gives consumers no reset time or phase; a provisional LTA looks settled

### Option 3: Publish raw values and document consumer-side filtering

Leave the payload unchanged and tell each consumer how to recognise and drop placeholder readings.

- *Advantages:* No app change; No heuristic in the app
- *Disadvantages:* Every consumer reimplements the same detection, and most will not; Retained 0 values keep poisoning history and alerts

## Decision Matrix

| Criterion | Persisted reset tracker with measurement_state | Stateless zero filter | Publish raw values and document consumer-side filtering |
| --- | --- | --- | --- |
| Prevents false radon zeros | 5 | 5 | 1 |
| Flags a provisional long-term average | 5 | 1 | 2 |
| Implementation and maintenance cost | 3 | 5 | 4 |
| Consumer effort | 5 | 4 | 1 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Battery changes no longer write 0 Bq/m³ into Home Assistant or long-term databases
- measurement_state and sensor_reset_at are retained diagnostic entities, so a fresh LTA is visible as provisional
- Reset detection is a pure, fully unit-tested function; the handler only loads and saves its state
- The INFO log names the LTA that the reset wiped

### Negative

- A deployment whose radon is genuinely 0/0 Bq/m³ would see null until the first non-zero value; no setting overrides this until a user needs it
- A reset that happens while the app is down and ends before it restarts is only seen through the LTA-collapse rule, which needs a previous LTA of at least 20 Bq/m³
- The state payload gains two keys, which changes the Home Assistant entity set by two diagnostic sensors

_2026-10-04_
