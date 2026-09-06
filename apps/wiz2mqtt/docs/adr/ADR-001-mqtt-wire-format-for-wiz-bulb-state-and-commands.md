---
status: Accepted
date: 2026-09-06
impact: high
tags: [mqtt, serialization, architecture, telemetry]
---

# ADR-001: MQTT Wire Format for WiZ Bulb State and Commands

## Status

Accepted **Date:** 2026-09-06

## Context

wiz2mqtt publishes one retained payload per bulb on `wiz2mqtt/{bulb}/state` and accepts partial updates on `wiz2mqtt/{bulb}/set`, and both topics must be consumed natively by **two** home-automation controllers at once: Home Assistant via MQTT discovery, and openHAB via a Generic MQTT Thing. There is no translating bridge between them.

Home Assistant's MQTT `light` platform offers two payload styles. `schema: json` carries the whole light in one JSON object (`state`, `brightness`, `color_mode`, `color`, `color_temp`, `effect`); `schema: default` spreads each attribute across its own `*_state_topic` / `*_command_topic`. HA accesses `values["state"]` unconditionally and discards the entire message on a `KeyError`, so once `schema: json` is chosen the object shape is fixed, not negotiable.

openHAB's Generic MQTT Thing binds each channel to a single JSONPath scalar (`$.state`, `$.brightness`, ...). It has no HSV-from-RGB transform and its Color channel wants one `"h,s,b"` string. The HA `color: {r,g,b}` object is therefore unusable for openHAB's Color channel directly.

Internally, colour is held as `(hue, saturation, dimming)` — pywizlight's own `hucolor` convention (hue 0..360, saturation 0..100). pywizlight's `rgb=` command path discards luminance entirely, so colour must always be *applied* as hue/saturation plus a separate brightness, never as an RGB triple; RGB is reconstructed via standard HSV→RGB only to fill HA's `color` object on the state topic.

## Decision

Use Home Assistant's MQTT light `schema: json` object as the canonical wire format for every `wiz2mqtt/{bulb}/state` and `/set` payload, extended with one non-HA `hsb` string key (`"h,s,b"`, hue 0-359, saturation and brightness 0-100) that Home Assistant silently ignores and openHAB consumes as a native Color item, and keep the internal canonical colour state as `(hue, saturation, dimming)` with RGB reconstructed via HSV→RGB only to populate HA's `color` object.

```json
{
  "state": "ON",
  "brightness": 128,
  "color_mode": "rgb",
  "color": {"r": 255, "g": 170, "b": 80},
  "hsb": "32,69,50"
}
```

## Decision Drivers

- Home Assistant and openHAB must consume the identical retained topic with no translating bridge in between
- HA discards a light payload entirely on a missing `state` key, so the JSON object shape is not negotiable once `schema: json` is chosen
- openHAB's Generic MQTT Thing binds a channel to a single JSONPath scalar and has no HSV-from-RGB transform, so it needs a ready-made `"h,s,b"` colour value on the wire
- pywizlight's `rgb=` path discards luminance, so colour must be carried and applied as hue/saturation plus a separate brightness, never as an RGB triple
- A single wire representation keeps `build_state_payload`, the command translator and the colour helpers to one shape instead of three
- HA ignores unknown keys (verified against the 2026.8 source), so an extra `hsb` key costs nothing on the HA side

## Considered Options

### Option 1: HA schema: json object plus an hsb key (chosen)

Adopt HA's `schema: json` light object verbatim as the canonical payload for both `/state` and `/set`, and append one extra `hsb` string key for openHAB's Color channel. HA ignores the extra key; openHAB reads `$.hsb` and each other scalar it needs.

- *Advantages:* One retained topic and one command topic per bulb serve both controllers; HA MQTT discovery consumes it with zero custom templating; openHAB gets a native Color value without an HSV transform it cannot express; The internal `(hue, saturation, dimming)` model maps directly onto `hsb`, and RGB is a pure derived view
- *Disadvantages:* The payload carries colour twice — once as `color: {r,g,b}` for HA and once as `hsb` for openHAB — so a producer bug can make them disagree; `hsb` is a wiz2mqtt convention with no discovery-time schema on either side; openHAB hue is 0-359 while HA is 0-360, a one-unit domain mismatch that has to be documented rather than enforced

### Option 2: HA schema: default topic-per-attribute light

Use HA's `schema: default` light, publishing `state`, `brightness`, `rgb_color`, `color_temp` and `effect` each on its own state and command topic, and point openHAB channels at those flat scalar topics directly.

- *Advantages:* Every value is already a flat scalar, so openHAB needs no JSONPath at all; Each attribute has an explicit HA discovery key with its own schema; No duplicated colour representation on the wire
- *Disadvantages:* Roughly ten topics per bulb instead of two, multiplied across a 14-bulb inventory; Colour still arrives as `rgb_color` with no luminance, so the pywizlight `rgb=` luminance-loss problem is now on the wire, not just in the SDK call; Partial multi-field updates (`{"state": "ON", "brightness": 128}`) are no longer expressible in one message; Retained-topic cleanup and availability now span many topics per removed bulb

### Option 3: Custom neutral JSON with per-consumer bridges

Define a wiz2mqtt-native JSON schema optimised for the domain model and run a small translation layer (an HA MQTT template / an openHAB transform profile, or a second bridge process) to adapt it to each controller.

- *Advantages:* The wire format can match the internal `(hue, saturation, dimming)` model exactly with no derived views; Neither controller's quirks constrain the schema
- *Disadvantages:* Every consumer needs bespoke templating or a second moving part to maintain; Defeats the point of MQTT discovery — HA users would hand-write configuration again; Two translation surfaces to keep in sync with the schema on every change; openHAB's transform options cannot do HSV-from-RGB, so a bridge process is effectively mandatory

## Decision Matrix

| Criterion | HA schema: json object plus an hsb key | HA schema: default topic-per-attribute light | Custom neutral JSON with per-consumer bridges |
| --- | --- | --- | --- |
| Home Assistant discovery fit (zero custom templating) | 5 | 4 | 1 |
| openHAB Generic MQTT Thing fit | 4 | 4 | 2 |
| MQTT topics per bulb (fewer is better) | 5 | 2 | 4 |
| Colour + luminance fidelity | 4 | 2 | 5 |
| Implementation and test surface | 4 | 3 | 1 |
| Partial multi-field command updates in one message | 5 | 1 | 5 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- One retained `/state` topic and one `/set` topic per bulb serve Home Assistant and openHAB at once
- Home Assistant MQTT discovery (`app.discovery()`) and the offline `cosalette schema ha-discovery` path both emit the `light` entity with no hand-written templates
- openHAB's Color channel binds straight to `$.hsb`; the dimmer, switch and string channels bind to `$.brightness`, `$.state`, `$.effect`
- The canonical `(hue, saturation, dimming)` model has exactly one wire projection (`hsb`); `color: {r,g,b}` is a derived HSV→RGB view that never feeds a pywizlight `rgb=` call
- `state` is mandatory in every published payload, matching HA's unconditional `values["state"]` access

### Negative

- Colour is represented twice on the wire (`color` and `hsb`), so `build_state_payload` must keep them consistent and is tested to that effect
- `hsb` is a wiz2mqtt convention with no discovery-time schema on either controller
- The openHAB 0-359 vs HA 0-360 hue domain gap is handled by documentation and a `% 360` in the payload, not by a conversion layer
- Adopting HA's object shape means HA's future `schema: json` changes are a wire-format concern for wiz2mqtt

_2026-09-06_
