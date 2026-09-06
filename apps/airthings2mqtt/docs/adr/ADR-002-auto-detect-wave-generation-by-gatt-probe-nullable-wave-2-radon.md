---
status: Accepted
date: 2026-09-06
impact: moderate
tags: [devices, telemetry, serialization, architecture]
---

# ADR-002: Auto-detect Wave generation by GATT probe; nullable Wave 2 radon

## Status

Accepted **Date:** 2026-09-06

## Context

airthings2mqtt v0.1.5 speaks only the 1st-generation Airthings Wave BLE protocol: four fixed characteristic reads (`00002a6e`, `00002a6f`, `b42e01aa`, `b42e0a4c`). A 2nd-generation "Wave Radon" unit (model `2950`) exposes none of them. Its first `read_gatt_char` raises `BleakCharacteristicNotFoundError` and the poll aborts with no data published; the device never reaches `availability = online`.

An early-adopter field capture (ff-fab, 2026-09-05, `docs/planning/wave2-device-capture.md`) confirmed at the GATT level that every value the app needs lives in a single read-only proprietary characteristic, `b42e4dcc-ade7-11e4-89d3-123b93f75cba` ("Current Sensor Values"): 20 bytes, `struct.unpack("<4B8H", data)`, then `humidity = val[1] / 2.0`, `radon_short = val[4]`, `radon_long = val[5]`, `temperature = val[6] / 100.0`. This matches the decoder the community `airthings-ble` library (the package Home Assistant's `airthings_ble` integration depends on) ships for model 2950. No pairing, bonding, or Access Control Point handshake is required — the transport flow is exactly the existing connect/read/disconnect cycle, one read instead of four. The two generations are visually identical, so an operator cannot reliably tell which protocol a given unit speaks.

The community decoder also applies a `0..16383` Bq/m³ sanity bound to both radon fields, returning "no value" outside it — a cheap guard against a garbled frame (e.g. the `0xFFFF` sentinel that unused Wave Plus slots carry) publishing a wild radon number into Home Assistant history and radon automations. `AirthingsReading.radon_24h_avg` / `radon_long_term_avg` were plain `int`, so adopting the bound requires a type decision.

## Decision

Auto-detect the Wave generation on every BLE connection by probing `client.services.get_characteristic()` for the 2nd-gen "current values" characteristic `b42e4dcc` and dispatching to a per-generation pure decoder; a device without it falls through to the unchanged 1st-gen four-read path. No new configuration surface is added. Decode an implausible Wave 2 radon value (outside `0..16383` Bq/m³) to `None`, widening `AirthingsReading.radon_24h_avg` / `radon_long_term_avg` to `int | None`; because `_telemetry` returns an already-valid instance on cosalette's EAFP dump path, `None` is published as an explicit JSON `null` on the state topic, never an omitted key. Temperature and humidity are passed through unbounded, matching the 1st-gen path.

```python
async with BleakClient(mac) as client:
    if client.services.get_characteristic(_UUID_WAVE2_DATA) is not None:
        reading = _parse_wave2(await client.read_gatt_char(_UUID_WAVE2_DATA))
    else:
        reading = _parse_wave1(
            await client.read_gatt_char(_UUID_TEMPERATURE),
            await client.read_gatt_char(_UUID_HUMIDITY),
            await client.read_gatt_char(_UUID_RADON_24H),
            await client.read_gatt_char(_UUID_RADON_LTA),
        )


def _bounded_radon(value: int) -> int | None:
    return value if 0 <= value <= _RADON_MAX else None
```

## Decision Drivers

- The existing core-02 1st-gen deployment must keep working with no env-var change and no redeploy.
- The two Wave generations are physically indistinguishable, so requiring the operator to declare the protocol is error-prone.
- A BLE connect plus service discovery already dominates each poll's latency budget; an extra in-memory service lookup is effectively free.
- Wave Plus (b42e2a68) and Wave Mini (b42e3b98) should be addable later as one more probe branch each, without new configuration.
- A garbled BLE frame must not publish a false radon spike into Home Assistant history or radon-triggered automations.

## Considered Options

### Option 1: Probe GATT services per connection (chosen)

Before reading, ask the already-discovered service collection whether the 2nd-gen `b42e4dcc` characteristic exists; branch to the matching decoder. No configuration change; the 1st-gen path is byte-identical.

- *Advantages:* Zero-touch for the existing 1st-gen deployment — no setting, no redeploy.; Self-heals if a unit is later swapped or its firmware changes protocol generation.; Extends to Wave Plus / Wave Mini by adding one more `get_characteristic()` branch each.; Mirrors the community reference implementation, which also enumerates characteristics rather than assuming a fixed layout.
- *Disadvantages:* One extra in-memory service lookup per poll (negligible next to BLE connect cost).; A MAC pointing at a non-Airthings device that exposes neither char set fails per-poll with `BleReadError` rather than a fast config error.

### Option 2: Explicit AIRTHINGS2MQTT_DEVICE_PROTOCOL setting

Add a `wave1` | `wave2` setting (default `wave1`) and dispatch on it, never probing the device.

- *Advantages:* Fails fast with a clear error when misconfigured.; Dispatch logic is trivial and needs no GATT introspection to test.
- *Disadvantages:* Adds a config knob every operator must look up and set correctly for a distinction they cannot see on the hardware.; Does not self-heal when a device is replaced with a different generation.; Existing deployments gain a setting they must now be aware of even to keep the default.; Each further generation (Plus, Mini) widens the enum and the docs.

### Option 3: Dispatch on the DIS model number (0x2a24)

Read the Device Information Service model-number string (`2900`, `2920`, `2930`, `2950`, …) and map it to a decoder, the way the community `device_type.py` does.

- *Advantages:* Zero configuration, like the chosen option.; One authoritative signal that also names the exact hardware for logging.
- *Disadvantages:* Adds a second mandatory GATT read (the model string) to every poll.; Needs a model-number → decoder table kept in sync with Airthings' catalogue; an unknown future model has no fallback.; Indirection: the model number identifies the product, not the GATT contract, so a firmware change that alters the layout without changing the model number would be misrouted.

## Decision Matrix

| Criterion | Probe GATT services per connection | Explicit AIRTHINGS2MQTT_DEVICE_PROTOCOL setting | Dispatch on the DIS model number (0x2a24) |
| --- | --- | --- | --- |
| Zero-touch for the existing 1st-gen deployment | 5 | 2 | 5 |
| Self-heals on device swap / firmware change | 5 | 2 | 3 |
| Operator cognitive load | 5 | 2 | 5 |
| Extensibility to Wave Plus / Wave Mini | 5 | 3 | 3 |
| Implementation and test complexity | 4 | 3 | 3 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- The core-02 1st-gen deployment is unaffected: no env var, no redeploy, and its unit tests assert the four-read path is byte-identical.
- A 2nd-gen Wave Radon (model 2950) is read successfully with no configuration change.
- Wave Plus and Wave Mini can be added later as one more probe branch plus one more pure decoder, with no new config surface.
- A corrupted or sentinel Wave 2 radon value surfaces as JSON `null` (Home Assistant reads it as "unknown") instead of a false spike feeding radon history and automations.
- Both decoders are pure functions over raw bytes, unit-tested — including against a captured real-device frame cross-checked with the official Airthings app.

### Negative

- `radon_24h_avg` and `radon_long_term_avg` are now nullable in the AsyncAPI schema and on the wire; downstream consumers must tolerate `null`.
- Each poll performs one extra in-memory service lookup after connect.
- A MAC that resolves to a device exposing neither characteristic set fails per-poll with `BleReadError` rather than a startup configuration error.
- Wave 2 temperature and humidity are passed through unbounded, unlike the community reference, which caps them — a deliberate scope limit, since a bad temperature is far less harmful than a false radon reading and the 1st-gen path is likewise unbounded.

_2026-09-06_
