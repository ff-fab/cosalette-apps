---
status: Accepted
date: 2026-09-06
impact: low
tags: [architecture, error-handling, mqtt, documentation]
---

# ADR-005: Legacy wizcontrol.py Defects Deliberately Not Reproduced

## Status

Accepted **Date:** 2026-09-06

## Context

wiz2mqtt replaces an untracked single-file script, `legacy/wizcontrol.py` (531 lines, `wiz/<lamp>/<attr>/{set,get}` → `wiz/<lamp>/<attr>/actual` topic grammar). The rewrite is a clean reimplementation from the wire-format (ADR-001) and colour-model specs, with no backward compatibility. Before the script is deleted (cap-10u.20 — it is never committed to git, so this ADR is its behavioural record), the defects that a faithful port would have carried forward are catalogued here so nobody later 'restores' one as a feature.

### Catalogued defects (not reproduced)

1. **`power/actual` is always `"ON"`.** `evaluate_msg` publishes `"ON" if power else "OFF"` where `power` is the *string* returned by `get_power()` (`"ON"` / `"OFF"` / `"UNDEF"`). Every non-empty string is truthy, so `"OFF"` and `"UNDEF"` both publish `"ON"` (`wizcontrol.py:365-367`, `370-373`).
2. **`turn_off` never awaits its work.** `asyncio.gather(*[bulb.turn_off() ...])` is created and discarded, then the function returns (`:99-102`) — the turn-off coroutines may never run, and the loop logs 'coroutine was never awaited' on teardown.
3. **`turn_off` has no timeout** unlike `turn_on` (`:105-112`), so combined with (2) a hung bulb is unbounded.
4. **Uncaught `KeyError` in `set_speed`.** `SCENE_NAME_TO_ID[scene]` with `scene = await get_scene(light)`, which can be `"NULL"`, `"UNDEF"` or `None` (`:216-221`). The exception unwinds through `evaluate_msg` and the message loop, past `except aiomqtt.MqttError`, killing the process.
5. **`literal_eval` on the raw MQTT payload** in `rgb/set` with no `try`/`except` (`:419`) — a malformed payload raises `ValueError` / `SyntaxError` and crashes the loop; any literal shape/length is accepted.
6. **No range validation on r/g/b** in `set_rgb` (`:261-286`), unlike `brightness`, `speed` and `temperature`, which are bounds-checked before use.
7. **Colour set via `rgb=(r,g,b)`** (`:263`), whose pywizlight path discards luminance — brightness sent alongside a colour is lost.
8. **`set_state` awaits an already-cancelled gather.** After `asyncio.wait_for(..., timeout)` times out and cancels the gather, `await set_state` runs again with no `CancelledError` guard (`:87-96`), raising `CancelledError` out into callers.
9. **Cooperative cancellation is swallowed.** `set_scene`, `set_brightness`, `set_speed`, `set_rgb`, `set_temperature` and `get_state` catch `asyncio.CancelledError` and return `None` (`:133-134`, `:175-176`, ...), defeating the `BaseException` base that exists to stop exactly this.
10. **`get_state` awaits the same gather twice** (`:75`, `:80`).
11. **A 10-iteration confirmation poll after every setter** — `asyncio.sleep(0.1)` plus a 3 s `get_state` gather per iteration (`:137-154` and siblings), run inline in the one message loop, adding seconds of latency per command.
12. **`set_brightness`'s confirmation compares a hex string to `percent_to_hex(dim)`** (`:187`); percent↔hex rounding rarely matches exactly, so the loop almost always runs all ten iterations and falls through to the fallback `updateState()` — pure dead latency.
13. **`brightness/set` accepts `dim == 0`** (`:392`) then `percent_to_hex(0)`; 0 % is outside a WiZ bulb's real dimming range and behaves unpredictably.
14. **One global serial message loop.** `async for message in mqttc.messages` awaits `evaluate_msg` inline (`:504-521`), so one unreachable bulb group stalls all 18 entities — no per-entity dispatch.
15. **Supervision catches only `aiomqtt.MqttError`** (`:523`) — any `KeyError` / `ValueError` / `SyntaxError` from a handler kills the whole process; no per-entity error isolation.
16. **Import has side effects.** `sys.stdout` / `sys.stderr` are globally replaced with a file-logging shim at import time (`:67-69`) and MQTT credentials are module-level constants (`:13-16`) — the module cannot be imported for a test.
17. **Untyped magic strings on the wire.** `get_*` helpers return `"NULL"` / `"UNDEF"` / raw hex (`:161`, `:208-210`), so `brightness/actual` can carry a hex string while `brightness/set` wants an int 0-100; `rgb/actual` publishes a Python tuple repr via `str(rgb)` (`:422`).
18. **`get_speed` returns `act[0]` with no `None` guard** (`:256`), unlike its siblings that map `None` → `"UNDEF"`.
19. **A `None` `response_payload` is still published** — `mqttc.publish(topic, None)` when e.g. `set_scene` fails (`:520-521`), guarded only on `topic`.
20. **No retained messages, no availability/LWT topic** anywhere — a consumer cannot tell a bulb or the bridge is offline, and all state is lost on restart.

## Decision

Reimplement wiz2mqtt from the wire-format and colour-model specifications rather than porting `legacy/wizcontrol.py`, and treat none of the twenty catalogued behaviours above as a requirement. The cosalette archetypes supply correct versions of what the script hand-rolled: per-entity concurrent dispatch and error isolation, retained state with `exclude_none` shaping, framework-managed availability and LWT, bounded command timeouts, and validated payloads. The legacy script stays uncommitted and is deleted under cap-10u.20; this ADR is the record of what it did.

## Decision Drivers

- The rewrite is a clean reimplementation from specs with no compatibility target, so legacy behaviour is not something to match
- Several legacy behaviours are outright defects — process-killing exceptions, always-"ON" power, a turn-off that never runs — that a faithful port would carry forward
- cosalette already provides the infrastructure the script hand-rolled badly (per-entity dispatch, error isolation, retained state, availability/LWT, bounded timeouts), so mirroring the legacy structure would mean re-implementing its flaws
- A written record of what was deliberately dropped stops a future reader restoring a bug as a feature, and documents why `legacy/wizcontrol.py` is deleted without first being committed to git (cap-10u.20)

## Considered Options

### Option 1: Reimplement from spec, catalogue and drop the legacy defects (chosen)

Build wiz2mqtt fresh on cosalette from the ADR-001 wire format and the (hue, saturation, dimming) colour model. Record the legacy defects here and reproduce none of them. Delete the script under cap-10u.20.

- *Advantages:* None of the 20 defects survive into the new app; Correct behaviour comes from framework primitives, not re-derived hand-rolled loops; The behavioural record is preserved without keeping dead code in the tree; The new topic grammar (`wiz2mqtt/{bulb}/{state,set,availability}`) is designed for HA + openHAB discovery from the start
- *Disadvantages:* A consumer wired to the old `wiz/<lamp>/<attr>/actual` grammar must be reconfigured — there is no transition period; Any undocumented behaviour someone relied on is gone with no deprecation warning

### Option 2: Port the script structure, fix defects incrementally

Translate `wizcontrol.py` into the repo's layout roughly as-is, keeping its helper shape and topic grammar, then file a bug per defect and fix them over time.

- *Advantages:* Consumers keep working through the transition; Each fix is a small reviewable change against a known baseline
- *Disadvantages:* Ships 20 known defects on day one and relies on follow-through to remove them; The legacy structure (one serial loop, string sentinels, confirmation polls) fights cosalette's archetypes rather than using them; Carrying the old topic grammar blocks HA/openHAB discovery, which is the point of the rewrite

### Option 3: Keep wizcontrol.py running as a compatibility bridge

Run the legacy script alongside wiz2mqtt indefinitely, bridging the old `wiz/...` topics to the new ones for consumers that have not migrated.

- *Advantages:* Zero migration effort for existing consumers
- *Disadvantages:* Two processes talking to the same bulbs over connectionless UDP, racing each other's writes; The defects stay live in production forever; Doubles the operational surface and the push-port contention (ADR-004) to avoid a one-time reconfiguration

## Consequences

### Positive

- wiz2mqtt starts life with none of the catalogued defects and with per-entity error isolation from the framework
- The legacy behavioural record survives the deletion of the code (cap-10u.20)
- The new topic grammar is discovery-ready for both Home Assistant and openHAB
- Test coverage targets the correct behaviour directly rather than pinning legacy quirks

### Negative

- No compatibility window: consumers on the `wiz/<lamp>/<attr>/actual` grammar must be reconfigured in one step
- Undocumented legacy behaviours that someone depended on are gone without a deprecation path
- This ADR must be kept as the sole record once `legacy/wizcontrol.py` is removed

_2026-09-06_
