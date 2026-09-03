# Proposal: support the Airthings Wave 2 / Wave Radon (2nd-gen) BLE protocol

**Routed to:** **airthings2mqtt** app maintainer
**Type:** enhancement proposal (not a bug against existing behaviour)
**Source:** deploying a second, physically identical "Airthings Wave Radon" unit
on edge-01 (jl4 fleet), sibling to the working core-02 instance.
**Date:** 2026-08-27 · **Tracking:** jl4-8xo

**Status (2026-09-03):** open, unimplemented. Now tracked in beads as
`cap-awb` (the adapter work, Option A) and `cap-7x2` (the docs-claim
correction, which is independently landable). Re-checked against the
current adapter and against cosalette 0.8.0: nothing here is superseded —
the split is entirely in the devices' GATT tables and is orthogonal to the
framework upgrade. The type caveat below still applies verbatim
(`AirthingsReading.radon_24h_avg` / `radon_long_term_avg` are plain `int`
in `ports.py`), and all three doc claims flagged under "Related" are still
present.

---

## Summary

The current adapter (`packages/src/airthings2mqtt/adapters/bleak.py`, as of
release `v0.1.5`, the latest tag) only speaks the **1st-generation Wave**
BLE protocol — four fixed characteristic reads:

```python
_UUID_TEMPERATURE = "00002a6e-0000-1000-8000-00805f9b34fb"
_UUID_HUMIDITY = "00002a6f-0000-1000-8000-00805f9b34fb"
_UUID_RADON_24H = "b42e01aa-ade7-11e4-89d3-123b93f75cba"
_UUID_RADON_LTA = "b42e0a4c-ade7-11e4-89d3-123b93f75cba"
```

`docs/getting-started.md` claims support for "Wave, Wave Plus, or Wave Mini",
but the code implements none of the newer protocols — only the original Wave.
A second, newer-generation "Wave Radon" unit fails outright:

```
BleakCharacteristicNotFoundError: Characteristic 00002a6e-0000-1000-8000-00805f9b34fb was not found!
```

This proposal adds support for the **Wave 2 / Wave Radon (2nd-gen)**
protocol — the specific generation we hit — with a design that also leaves
room for Wave Plus / Wave Mini to be added the same way later, and flags the
docs claim that should be corrected either way.

---

## Evidence: two visually-identical units, two different GATT protocols

| | core-02's sensor (works today) | edge-01's sensor (fails) |
|---|---|---|
| MAC | `f0:f8:f2:xx:xx:xx` | `04:ee:03:xx:xx:xx` |
| Manufacturer ID | `0x0334` (Airthings) | `0x0334` (Airthings) |
| Data exposed via | standard BLE SIG chars `0x2a6e`/`0x2a6f` + custom `b42e01aa`/`b42e0a4c` | proprietary "current values" char `b42e4dcc-ade7-11e4-89d3-123b93f75cba` |

Full characteristic dump of the failing device, captured with
`gatttool -b 04:EE:03:XX:XX:XX --characteristics` after confirming BLE
reachability (this bypasses the app entirely — it's raw BlueZ/gatttool, so
the divergence is confirmed to be in the device's GATT table, not in
bleak/BlueZ tooling):

```
handle = 0x000c, char properties = 0x02 (read),                     uuid = b42e4dcc-ade7-11e4-89d3-123b93f75cba
handle = 0x000f, char properties = 0x2c (write/write-no-resp/indicate), uuid = b42e50d8-ade7-11e4-89d3-123b93f75cba
handle = 0x0013, char properties = 0x10 (notify),                    uuid = b42e538a-ade7-11e4-89d3-123b93f75cba
```

No `0x2a6e`/`0x2a6f`/`b42e01aa`/`b42e0a4c` characteristics exist on this
device at all — the adapter's four fixed reads have nothing to find. The
sensor data is fully available via a **single plain read** of `b42e4dcc`
(properties `0x02` = read-only, no pairing/notify/write handshake needed);
`b42e50d8`/`b42e538a` appear to be a separate write/notify command channel
(likely used by the official app for config or OTA) and are not needed for
telemetry.

---

## Background: Airthings' three (at least) GATT protocol generations

This is a known, previously reverse-engineered split — not something new we
discovered from scratch. The community Home Assistant integration
[`custom-components/sensor.airthings_wave`](https://github.com/custom-components/sensor.airthings_wave)
(MIT-licensed) documents and implements decoders for all of them in
[`custom_components/airthings_wave/airthings.py`](https://github.com/custom-components/sensor.airthings_wave/blob/master/custom_components/airthings_wave/airthings.py):

```python
CHAR_UUID_TEMPERATURE = UUID('00002a6e-0000-1000-8000-00805f9b34fb')       # 1st-gen Wave
CHAR_UUID_HUMIDITY = UUID('00002a6f-0000-1000-8000-00805f9b34fb')         # 1st-gen Wave
CHAR_UUID_RADON_1DAYAVG = UUID('b42e01aa-ade7-11e4-89d3-123b93f75cba')    # 1st-gen Wave
CHAR_UUID_RADON_LONG_TERM_AVG = UUID('b42e0a4c-ade7-11e4-89d3-123b93f75cba')  # 1st-gen Wave
CHAR_UUID_WAVE_PLUS_DATA = UUID('b42e2a68-ade7-11e4-89d3-123b93f75cba')   # Wave Plus (+CO2/VOC/pressure)
CHAR_UUID_WAVE_2_DATA = UUID('b42e4dcc-ade7-11e4-89d3-123b93f75cba')      # Wave 2 / Wave Radon (2nd-gen) <-- what we need
CHAR_UUID_WAVEMINI_DATA = UUID('b42e3b98-ade7-11e4-89d3-123b93f75cba')    # Wave Mini
```

The `b42e4dcc` UUID matches exactly what `gatttool` found on the edge-01
device, confirming it's a Wave 2 / Wave Radon (2nd-gen) unit.

### Decode format (from the same reference implementation)

```python
class Wave2Decode(BaseDecode):
    def decode_data(self, raw_data):
        val = struct.unpack('<4B8H', raw_data)  # 4 unsigned bytes + 8 unsigned shorts, little-endian, 20 bytes
        return {
            'humidity': val[1] / 2.0,
            'radon_1day_avg': val[4] if 0 <= val[4] <= 16383 else None,
            'radon_longterm_avg': val[5] if 0 <= val[5] <= 16383 else None,
            'temperature': val[6] / 100.0,
        }
```

Notes on this layout (`val[0]`..`val[3]` are the leading bytes, `val[4]`..`val[11]`
are the eight shorts that follow):
- `val[0]` — protocol/format version byte (unused by the decoder above; worth
  logging at DEBUG so a future firmware bump that changes layout is visible).
- `val[1]` — humidity, raw value is %RH × 2.
- `val[2]`, `val[3]` — not decoded by the reference implementation (likely
  ambient-light / accelerometer-adjacent bytes, mirroring the equivalent
  positions in `WavePlussDecode`; not needed for our fields).
- `val[4]` — radon 24h/1-day average, Bq/m³, with the reference
  implementation's own sanity bound (`0`–`16383`) — worth keeping, it's cheap
  insurance against a garbled read producing a wild number downstream.
- `val[5]` — radon long-term average, Bq/m³, same bound.
- `val[6]` — temperature, raw value is °C × 100 (signed handling not needed
  here since the format uses unsigned `H`, matching the reference; the
  existing 1st-gen adapter uses signed `h` for temperature — worth
  double-checking against a real device during implementation, since indoor
  temperature is never negative in practice but the wire format's signedness
  should still be gotten right).
- `val[7]`+ — present in the Wave Plus layout (pressure/CO2/VOC) but **not**
  decoded for Wave 2 by the reference implementation — the Wave Radon
  hardware doesn't have those sensors, so this is expected, not a
  simplification worth reproducing exactly rather than guessing at.

This mirrors the structure of `_UUID_TEMPERATURE`/`_UUID_HUMIDITY` parsing
already in `bleak.py` (`struct.unpack("<h", raw_temp)[0] / 100.0` etc.) —
same style, just one read instead of four, and one struct instead of four.

---

## Proposed implementation

Two design options, in order of preference:

### Option A (recommended): auto-detect protocol generation per connection

Since `BleakAirthingsReader.read()` already does a full connect/disconnect
cycle per poll (not a persistent connection), the extra cost of a service
lookup before reading is negligible — BLE connect setup already dominates
the latency budget, and polling is on the order of minutes
(`AIRTHINGS2MQTT_POLL_INTERVAL`, default ≥60s, currently `1500` in this
fleet).

Sketch (illustrative, not a literal patch):

```python
_UUID_WAVE2_DATA = "b42e4dcc-ade7-11e4-89d3-123b93f75cba"

async def read(self, mac: str) -> AirthingsReading:
    async with BleakClient(mac) as client:
        wave2_char = client.services.get_characteristic(_UUID_WAVE2_DATA)
        if wave2_char is not None:
            raw = await client.read_gatt_char(_UUID_WAVE2_DATA)
            return self._parse_wave2(raw)

        # existing 1st-gen path — unchanged
        raw_temp = await client.read_gatt_char(_UUID_TEMPERATURE)
        raw_hum = await client.read_gatt_char(_UUID_HUMIDITY)
        raw_radon_24h = await client.read_gatt_char(_UUID_RADON_24H)
        raw_radon_lta = await client.read_gatt_char(_UUID_RADON_LTA)
        return self._parse_wave1(raw_temp, raw_hum, raw_radon_24h, raw_radon_lta)

@staticmethod
def _parse_wave2(raw: bytes) -> AirthingsReading:
    val = struct.unpack("<4B8H", raw)
    radon_24h = val[4] if 0 <= val[4] <= 16383 else None
    radon_lta = val[5] if 0 <= val[5] <= 16383 else None
    return AirthingsReading(
        temperature=val[6] / 100.0,
        humidity=val[1] / 2.0,
        radon_24h_avg=radon_24h,
        radon_long_term_avg=radon_lta,
    )
```

Advantages:
- No new config surface (`AIRTHINGS2MQTT_DEVICE_MAC` stays the only
  per-device setting) — existing core-02 deployment needs zero changes.
- Naturally extends to Wave Plus / Wave Mini later by adding another
  `get_characteristic()` branch each, without touching deployment config.
- Matches the reference implementation's own approach (`get_sensors()`
  there enumerates `service.characteristics` and filters against a known-UUID
  set rather than assuming a fixed layout).

Caveat: `AirthingsReading.radon_24h_avg` / `radon_long_term_avg` would need
to become `int | None` (or the `None` sanity-bound behavior dropped) since
the current 1st-gen path always returns an `int`. Check
`packages/src/airthings2mqtt/ports.py` for how `AirthingsReading` is typed
and how the MQTT publisher handles a `None` reading field before deciding
whether to keep the bounds check or drop it.

### Option B (fallback, if auto-detect is undesirable): explicit config

Add `AIRTHINGS2MQTT_DEVICE_PROTOCOL` (`wave1` | `wave2`, default `wave1` to
preserve existing behaviour) and dispatch on that instead of probing
`client.services`. Simpler to reason about and test, but adds a config knob
users have to look up correctly, and doesn't self-heal if a device's
firmware is later swapped/upgraded to a different protocol generation.

Option A is recommended unless there's a reason (e.g. wanting to fail fast
with a clear config error rather than silently probing) to prefer B.

---

## Testing guidance

The reference implementation doesn't ship a byte-level test fixture for
Wave 2 that we can cite directly — capture a real raw sample from a Wave 2 /
Wave Radon device during implementation (e.g. `gatttool -b <mac>
--char-read -a 0x000d` against the edge-01 unit, or log the raw bytes at
DEBUG from a throwaway `read_gatt_char` call) and use that as the unit-test
fixture, the same way the existing 1st-gen tests presumably fixture
`raw_temp`/`raw_hum`/etc. Cross-check decoded values against the official
Airthings app's readings for the same device at the same time, the way the
original app-findings.md smoke test cross-checked 1st-gen temperature
(jl4-qob.5 — 32.8°C, confirmed correct decode, not a scaling bug).

---

## Related: `docs/getting-started.md` claim vs. actual support

The prerequisites table currently says:

> **Airthings Wave** — Wave, Wave Plus, or Wave Mini (BLE-capable)

but as of `v0.1.5` only the original Wave protocol is implemented, and none
of the three generations named there include the Wave 2 / Wave Radon variant
that prompted this proposal. Whatever the outcome of this proposal, the docs
should say what the code actually supports at the released version — either
scope the docs down to "Wave (1st-gen)" today, or land this proposal and
broaden the docs table to explicitly list Wave 2/Radon (and Plus/Mini,
if/when those also land).

---

## Routing rationale

This is app-specific (BLE adapter / protocol support), not a cosalette
framework issue — routed the same way as the existing findings in this
directory (`app-findings.md` vs `framework-findings.md`).
