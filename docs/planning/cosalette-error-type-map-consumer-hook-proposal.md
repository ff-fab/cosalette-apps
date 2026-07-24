# cosalette Framework Enhancement: Expose a consumer `error_type_map` hook so LEAK-01 redaction can be opted out per exception type

**Date:** 2026-07-23
**Author:** caldates2mqtt / jeelink2mqtt / vito2mqtt maintainer
**Status:** Awaiting framework implementation
**Context:** cosalette 0.5.6 shipped "LEAK-01" error-payload hardening. The hardening is
correct, but 0.5.6 removed (or never re-exposed) any consumer-facing way to register
app-level exception types into the redaction allow-list. Apps that already ship an
`error_type_map` (jeelink2mqtt, vito2mqtt) now carry **dead config** that the framework
never consumes, and caldates2mqtt has **two failing integration tests** as a direct
result.
**Related beads:** sibling of `cap-075` and `cap-nx5` (framework gaps surfaced by
cap-3bz); this is the higher-severity of the current framework gaps because it silently
degrades error diagnostics and has an active test failure.

---

## Executive Summary

cosalette 0.5.6 hardened error publishing (LEAK-01): `build_error_payload`
(`cosalette/_errors.py`, ~L130) publishes **only the exception class name** for any
exception type **not present** in the `ErrorPublisher`'s `error_type_map`, unless the
global `MqttSettings.error_publish_verbose` flag (env `MQTT__ERROR_PUBLISH_VERBOSE=true`)
is set. This default-deny behaviour prevents accidental leakage of sensitive data in
exception messages — a good default.

**But 0.5.6 exposes no public, consumer-facing way to register app-level exception types
into that map.** The `ErrorPublisher` is constructed once, deep in the wiring, with a
hard-coded framework-only map; no `App`/`app.run` parameter, decorator, or registration
API feeds app exception types into it. Consequently, domain exceptions that carry
**intentionally safe, informative** messages are redacted to bare class names, silently
degrading downstream MQTT error diagnostics.

**This proposal asks the framework to expose a public consumer hook — e.g.
`App(error_type_map=...)` and/or `app.run(error_type_map=...)` and/or a
registration/decorator API — that `create_services` merges into the `ErrorPublisher`'s
map, so apps can opt *specific* domain exception types back into full-message publishing
without resorting to the global verbose flag.** This preserves LEAK-01's default-deny
while restoring the targeted opt-in that jeelink2mqtt and vito2mqtt already assume
exists.

---

## Problem Statement

### LEAK-01 redacts everything not in the map, and the map is closed to apps

Traced wiring in cosalette 0.5.6:

1. `build_error_payload` (`cosalette/_errors.py` ~L130): for an exception whose type is
   **not** a key in `error_type_map`, it publishes only the class name unless the global
   `error_publish_verbose` flag is set.
2. The `ErrorPublisher` is built **once** in
   `cosalette/_wiring/_infra.py:77-82` (`create_services`) with
   `error_type_map=dict(_FRAMEWORK_ERROR_TYPE_MAP)` — a hard-coded copy.
3. `_FRAMEWORK_ERROR_TYPE_MAP` (`cosalette/_runners/_command_runner.py:55`) contains only
   **3 framework command exceptions**.
4. `App.__init__`, `App.run`, and the `@app.telemetry` / `@app.command` / `@app.device`
   decorators take **no** `error_type_map` parameter.
5. The `ErrorPublisher` dataclass field is never mutated after construction.

There is therefore **no supported path** from application code into the map that governs
redaction. An app cannot say "publish the full message for *this* domain exception"
without reaching around the framework.

### Apps already ship maps the framework silently ignores

Both jeelink2mqtt (`errors.py:30`) and vito2mqtt (`errors.py:48`) define an
`error_type_map` with docstrings stating that cosalette's `ErrorPublisher` consumes them.
In 0.5.6 these maps are **dead config** — never wired in. This strongly suggests a prior
cosalette version consumed a consumer hook that 0.5.6 dropped or omitted, leaving the
app-side maps stranded.

### Impact

Domain exceptions that carry deliberately safe, human-useful messages are redacted to
class names on the MQTT error topic, silently degrading operational diagnostics:

- **caldates2mqtt (active failure):** `CalDavConnectionError` / `CalDavNotFoundError`
  carry messages like `"server unreachable"` and `"calendar not found"`. Under LEAK-01
  these are redacted to the class name, and **two integration tests fail** because they
  assert the informative message text on the error topic.
- **jeelink2mqtt + vito2mqtt (latent exposure):** both ship an `error_type_map` that is
  never wired in, so their domain exceptions are *also* redacted today. Their suites pass
  only because no test asserts message text on the error topic — the exposure is latent,
  not absent.
- **Any future app with domain exceptions** inherits the same trap.

### The only current workarounds are all bad

1. **Global `error_publish_verbose` / `MQTT__ERROR_PUBLISH_VERBOSE=true`** — un-redacts
   **every** exception in the process, including framework and third-party exceptions
   whose messages may contain secrets (CalDav URLs with embedded credentials, broker
   passwords, tokens). This defeats LEAK-01 entirely and re-opens the exact threat the
   hardening addresses.
2. **Mutating the private `_FRAMEWORK_ERROR_TYPE_MAP`** — a fragile backdoor around a
   security feature, reaching into framework internals that can change without notice.
3. **App-side catch-and-publish** — every handler wraps its domain calls, catches, and
   publishes a hand-built error payload, duplicating the framework's error-topic
   contract. This is an architectural burden and throwaway work the moment a proper hook
   exists.

---

## Proposed Solution

### A public consumer hook merged into the ErrorPublisher's map

Expose a supported way for an app to register an app-level `error_type_map` that
`create_services` **merges** into the `ErrorPublisher`'s map at construction. Candidate
surfaces (any one, or a combination):

```python
# Option A — constructor parameter
app = cosalette.App(
    name="caldates2mqtt",
    ...
    error_type_map={
        CalDavConnectionError: ErrorSpec(...),
        CalDavNotFoundError: ErrorSpec(...),
    },
)

# Option B — run-time parameter
app.run(error_type_map={...})

# Option C — registration / decorator API
app.register_error_types({CalDavConnectionError: ..., CalDavNotFoundError: ...})
```

`create_services` (`cosalette/_wiring/_infra.py`) then builds the `ErrorPublisher` with
the framework map **merged with** the app-provided map, instead of a hard-coded copy of
`_FRAMEWORK_ERROR_TYPE_MAP` alone.

The value type of each entry should match whatever `error_type_map` already holds
internally today (the same shape the framework map uses and the same shape jeelink2mqtt
/ vito2mqtt already declare), so existing app-side maps become live with no restructuring.

### Merge precedence

Define an explicit precedence so behaviour is predictable:

- **Framework entries are authoritative** for the 3 framework command exceptions — an
  app cannot override or shadow framework error handling.
- **App entries extend** the map for app-owned exception types.
- A conflict where an app tries to register a type already owned by the framework should
  either be ignored (framework wins) or raise at registration time — the framework
  maintainer's call; either is acceptable so long as it is documented.

### Result: targeted opt-in, default-deny preserved

- LEAK-01 default-deny remains the default: unlisted exceptions are still redacted to
  class names.
- Apps opt **specific** domain exception types back into full-message publishing, with no
  global flag and no leakage of unrelated exception messages.
- jeelink2mqtt's and vito2mqtt's existing maps become live again, closing their latent
  exposure; caldates2mqtt's two failing tests can pass by registering its two CalDav
  exceptions.

---

## Impact on Existing Apps

| App | Today | After this change |
|-----|-------|-------------------|
| caldates2mqtt | 2 failing integration tests; CalDav messages redacted | Register `CalDavConnectionError` / `CalDavNotFoundError`; messages published, tests pass |
| jeelink2mqtt | `error_type_map` (`errors.py:30`) is dead config; latent redaction | Existing map goes live; domain messages published |
| vito2mqtt | `error_type_map` (`errors.py:48`) is dead config; latent redaction | Existing map goes live; domain messages published |
| any future app with domain exceptions | inherits the redaction trap | Opt-in per exception type |
| apps without domain exceptions | unaffected | unaffected (map optional) |

---

## What This Does NOT Change

- **LEAK-01 default-deny** — unchanged; unlisted exceptions are still redacted by
  default. This proposal adds a *targeted, explicit* opt-in, not a loosening of the
  default.
- **`error_publish_verbose`** — unchanged; the global flag still exists for operators who
  genuinely want everything un-redacted. This proposal makes it unnecessary for the
  common "one or two safe domain exceptions" case.
- **Framework error handling** — unchanged; framework command exceptions remain
  authoritative in the merged map.
- **Error-topic payload contract** — unchanged; only the redaction decision for
  app-registered types changes.

---

## Alternatives Considered

1. **Global `error_publish_verbose` / `MQTT__ERROR_PUBLISH_VERBOSE=true`.** Rejected: it
   un-redacts every exception in the process, defeats LEAK-01, and risks leaking secrets
   (CalDav URLs/credentials, broker passwords) carried in unrelated exception messages —
   the exact threat LEAK-01 was introduced to close.
2. **Mutating the private `_FRAMEWORK_ERROR_TYPE_MAP`.** Rejected: fragile backdoor around
   a security feature; depends on framework internals that can change without notice; no
   API contract.
3. **App-side catch-and-publish in every handler.** Rejected: duplicates the framework's
   error-topic contract, imposes an architectural burden on every handler, and is
   throwaway work once a proper hook exists.
4. **Do nothing.** Rejected: caldates2mqtt has an active test failure, jeelink2mqtt and
   vito2mqtt carry latent exposure with dead config that the framework silently ignores,
   and the degradation is invisible (class-name-only payloads look plausible until
   someone needs the message during an incident).

---

## Summary

LEAK-01 (0.5.6) redacts every exception message not present in the `ErrorPublisher`'s
`error_type_map`, but 0.5.6 exposes no consumer-facing way to add app-level exception
types to that map — the publisher is built once with a hard-coded framework-only map, and
no `App`/`app.run`/decorator surface feeds it. jeelink2mqtt and vito2mqtt already ship
`error_type_map`s that are now dead config, and caldates2mqtt has two failing tests
because its safe CalDav messages are redacted. This proposal exposes a public hook (an
`App`/`app.run` parameter and/or registration API) that `create_services` merges into the
publisher's map, with framework entries authoritative and app entries extending — so apps
opt specific domain exception types back into full-message publishing while LEAK-01's
default-deny remains intact.
