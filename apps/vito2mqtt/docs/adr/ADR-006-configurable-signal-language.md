# ADR-006: Configurable Signal Language (DE/EN)

## Status

Accepted **Date:** 2026-02-28

## Context

We know the German strings for operating modes (BA), switch valve states (USV), and
error codes (ES). These strings originate from Viessmann's own documentation — the
canonical labels for boiler states are German because Viessmann is a German manufacturer
and the Vitodens 200-W's internal vocabulary is German.

ADR-004 mandated "English signal names throughout the codebase" to make the project
accessible to international contributors. However, this mandate conflated two distinct
concepts:

1. **Signal keys** — the MQTT topic components and command registry names (e.g.,
   `flow_temperature`, `operating_mode`). These are structural identifiers that must be
   stable and English for interoperability.
2. **Signal values** — the human-readable strings decoded from enum-type data (e.g.,
   "Reduced operation" vs. "Red. Betrieb" for BA mode `0x01`). These are presentation
   labels that users read in their MQTT client or Home Assistant dashboard.

Real-world users of Viessmann boilers overwhelmingly reside in German-speaking markets
(Germany, Austria, Switzerland). These users expect the familiar Viessmann terminology
they see in their boiler's control panel and installation manual. Forcing English-only
values creates a disconnect between the MQTT payload and the physical device.

The affected data types are exclusively enum-type codecs that map byte values to
human-readable strings:

- **BA** — operating modes (Betriebsart): 6 modes
- **USV** — three-way switch valve states (Umschaltventil): 4 states
- **ES** — error codes (Fehlerspeicher): ~60 historical error descriptions

Other data types (IS10, IUNON, IU3600, RT, CT, TI, PR2, PR3) produce numeric values,
timestamps, or cycle timers that are inherently language-neutral and require no
translation.

## Decision

Use a **stateless codec with language parameter** for enum-type data encoding and
decoding because it preserves codec purity while enabling configurable language output.

The `decode()` and `encode()` functions for enum-type codecs (BA, USV, ES) accept a
`language` keyword argument defaulting to `"en"`:

```python
decode("BA", b"\x01", language="de")  # → "Red. Betrieb"
decode("BA", b"\x01", language="en")  # → "Reduced operation"
decode("BA", b"\x01")                 # → "Reduced operation" (default)
```

This **partially supersedes ADR-004's** "English signal names" mandate:

- Signal _keys_ (MQTT topic components, command registry names) **remain English always**
- Signal _values_ from enum-type codecs **are configurable DE/EN**
- The distinction is: keys are structural identifiers, values are presentation labels

A `signal_language` setting is added to `Vito2MqttSettings` (see ADR-005):

| Setting           | Type            | Default | Notes                                      |
| ----------------- | --------------- | ------- | ------------------------------------------ |
| `signal_language` | `Literal["de", "en"]` | `"en"`  | Language for enum-type codec values |

The caller (session controller or command executor) reads `signal_language` from settings
and passes it to the codec on each call. The codec itself holds no state and has no
dependency on the settings module — language is just another function argument.

## Decision Drivers

- User experience — German-speaking users see familiar Viessmann terminology that matches
  their boiler's control panel and installation manual
- International accessibility — English as default ensures the open-source community can
  use the project without configuration changes
- Purity — codecs remain pure functions with no internal state, no settings coupling, and
  deterministic output based solely on their arguments
- Testability — language behavior is tested by passing different `language` arguments,
  with no setup/teardown of global state or configuration mocks
- Extensibility — adding a third language (e.g., French for Viessmann's French market)
  requires only extending the translation dictionaries, with no API changes

## Considered Options

- **Option A: Stateless codec with language parameter** — `decode(type_code, data,
  language="en")` — codec is a pure function, caller passes language from settings
- **Option B: Language-aware codec class** — codec instantiated with language setting,
  stores it as instance state, e.g., `Codec(language="de").decode("BA", data)`
- **Option C: Post-processing translation layer** — codec always returns English, a
  separate `Translator` maps English strings to German after the fact

## Decision Matrix

| Criterion     | A: Stateless param | B: Codec class | C: Translation layer |
| ------------- | ------------------ | -------------- | -------------------- |
| Purity        | 5                  | 2              | 4                    |
| Testability   | 5                  | 3              | 4                    |
| Simplicity    | 5                  | 3              | 2                    |
| Performance   | 5                  | 4              | 3                    |
| Extensibility | 4                  | 4              | 4                    |
| **Total**     | **24**             | **16**         | **17**               |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- Codecs remain pure functions — easy to test, reason about, and compose without global
  state or dependency injection
- Language is explicit in the API — every call site documents which language it requests,
  making data flow transparent
- Adding a third language only requires extending the translation dictionaries, with no
  changes to function signatures or the settings schema beyond a new literal value
- MQTT keys remain stable English regardless of language setting, preserving topic
  structure compatibility across language changes
- German labels are preserved exactly as in Viessmann documentation (with typo
  corrections), maintaining fidelity to the original source material

### Negative

- Every call site that produces human-readable enum values must thread the `language`
  parameter through the call chain from settings to codec
- Translation tables must be maintained for each supported language in sync — adding a
  new BA mode requires updating both DE and EN dictionaries
- Two-language support may create user confusion about which strings appear where (keys
  are always English, values depend on setting) until documentation clarifies the
  distinction
- German strings in source code may trigger codespell false positives, requiring
  ignore-list entries for legitimate German words like "Betrieb" or "Warmwasser"

_2026-02-28_
