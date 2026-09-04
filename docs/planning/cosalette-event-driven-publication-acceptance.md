# Downstream acceptance: event-driven publication (cosalette 0.8.0)

- **Status:** complete — all sixteen validation criteria discharged
- **Discharges:** `cap-8au`, definition-of-done item D4 of
  [the event-driven publication proposal](cosalette-event-driven-publication-proposal.md)
- **Verified against:** cosalette 0.8.0, the installed wheel — assertions run against it,
  source claims read from it (`_runners/_notifier.py`, `_runners/_device_trigger.py`,
  `_runners/_telemetry_runner.py`, `_runners/_contracts.py`, `_wiring/_context.py`,
  `_wiring/_resolution.py`, `testing/_harness.py`, `testing/_clock.py`)
- **Decision record:**
  [ADR-005](../adr/ADR-005-event-driven-publication-adoption.md) — the repo-wide
  adoption decision this evidence backs
- **Adopting apps:** jeelink2mqtt, vito2mqtt and wiz2mqtt with `triggerable="local"`;
  airthings2mqtt and caldates2mqtt keep their pre-existing `triggerable=True` and
  gained only a `min_interval=` throttle

## Where the assertions live

| Suite                                                                     | Covers                                                  |
| ------------------------------------------------------------------------- | ------------------------------------------------------- |
| `packages/tests/unit/test_event_driven_acceptance.py`                     | criteria 1–16, on purpose-built minimal apps            |
| `apps/jeelink2mqtt/packages/tests/integration/test_event_driven_acceptance.py` | acceptance 2 — frame → publish in one virtual tick   |
| `apps/wiz2mqtt/packages/tests/integration/test_bulb_state_publication.py` | acceptance 3 — push → publish without the tick elapsing  |
| `apps/jeelink2mqtt/packages/tests/integration/test_stream_receiver.py`    | the receiver's own arming contract (pre-existing)        |

The framework criteria are contracts about cosalette, not about a bulb or a LaCrosse
frame, so they are asserted once at the repo root rather than twice in two app suites.
The two app-shaped acceptance items live with the app they name.

### Why the clock had to be replaced

`FakeClock.sleep` advances virtual time instantly (`testing/_clock.py:34-44`). Under it
every `interval=` collapses into a busy loop, so "published without waiting for a
scheduled tick" and "the tick fired immediately" are indistinguishable and every timing
assertion here would pass whether or not the feature existed.

Each suite therefore uses a `RealSleepClock` — a `FakeClock` whose `sleep` really waits
— with the heartbeat lifted out of the test window. `now()` then stays where the test
left it, which is what makes "no clock advance" falsifiable, and a publish inside the
window can only have been woken. This is the fourth and fifth hand-rolled copy of that
class in this repo; collecting them is [`cap-o9x`](#follow-ups).

## Criterion-by-criterion verdicts

### Core behaviour

| #   | Criterion                            | Verdict | Notes                                                                                                                    |
| --- | ------------------------------------ | ------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1   | Slots exist per expanded entity      | holds   | Restated against `EntityNotifier.entities`, the public projection of `TriggerConfig.build(...).slots`, rather than the internal the proposal named |
| 2   | A local notify publishes with no clock advance | holds | The assertion the proposal exists for. One publish, `now()` unmoved                                              |
| 3   | Only the named entity wakes          | holds   | Two sibling entities record zero handler entries and no publish                                                          |
| 4   | Coalescing                           | holds   | Five arms delivered while the handler is in flight produce exactly one re-run                                            |
| 5   | Unknown names fail loudly            | holds   | `UnknownEntityError`, naming the entity. Never a silent no-op                                                            |
| 6   | Thread safety                        | holds   | An `asyncio.to_thread` arm is delivered exactly once; a bad name raises **in the calling thread**, not inside `call_soon_threadsafe` |

### Parity — nothing about a woken run differs from a ticked run

| #   | Criterion                       | Verdict           | Notes                                                                                              |
| --- | ------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------- |
| 7   | `OnChange()` still gates        | holds             | Two wakes yielding an identical payload produce one retained publish                               |
| 8   | `state_model=` validation identical | holds as parity; fails as an absolute | See [criterion 8](#criterion-8-state_model-is-weaker-than-the-criterion-assumed) |
| 9   | Availability unchanged          | holds             | `mark_unavailable()` / `mark_available()` from a woken run, retained, both directions               |
| 10  | Topics unchanged                | holds             | The exact topic set for a woken entity is `{prefix}/{name}/state` and `.../availability`. No sub-topic |

### Non-regression — the ADR-004 discovery path must not move

| #   | Criterion                              | Verdict | Notes                                                                                              |
| --- | -------------------------------------- | ------- | -------------------------------------------------------------------------------------------------- |
| 11  | `app.asyncapi()` identical             | holds   | Compared as the retained `_meta/registry` payload, so the comparison is of the post-expand document an operator receives |
| 12  | `assert_discovery_topics_published` unchanged | holds | Config topic → payload map identical with and without local triggering; the helper's expectations are taken from the app *without* it and checked against the app *with* it |
| 13  | `consumer()` annotations unaffected    | holds   | `display_name`, `unit` and `state_class` reach the generated payload either way                    |

### Backward compatibility

| #   | Criterion                       | Verdict  | Notes                                                                                              |
| --- | ------------------------------- | -------- | -------------------------------------------------------------------------------------------------- |
| 14  | `triggerable=True` still means MQTT | holds | Still subscribes `{prefix}/{name}/set`; the notifier is given no slot for it and refuses to arm it. Live in airthings2mqtt and caldates2mqtt |
| 15  | Every existing registration form still resolves | holds | Framework half: the upstream suite. Downstream half: ADR-005's per-app verdict table read back off the live `App` objects — the declared trigger sources, and the apps carrying a `min_interval=`, are exactly the accepted ones |
| 16  | The registration-time guards    | **lifted — restated** | See [criterion 16](#criterion-16-both-guards-were-lifted)                                      |

## The three criteria that needed more than a verdict

### Criterion 8: `state_model=` is weaker than the criterion assumed

The criterion asserts two things at once, and only the second is about event-driven
publication.

**The parity half holds.** A woken run and a ticked run of the same handler, failing the
same way, publish byte-identical error payloads to `{prefix}/{name}/error` and suppress
the state publish identically.

**The absolute half does not hold, for any wake reason.** A `@app.telemetry` handler
returning a plain `dict` is never validated against its declared contract — neither the
return annotation nor `state_model=`. `normalize_return` (`_runners/_contracts.py:288-296`)
takes an EAFP fast path: `TypeAdapter(model).dump_python(value, mode="json")` first,
falling back to `validate_python` only when that raises. Pydantic serialises a plain
dict against a `BaseModel` adapter with a `UserWarning`, not an exception, so the
fallback never runs and a field of the wrong type is published verbatim. Validation does
engage when the value cannot be serialised at all, which is the failure the parity
assertion above uses.

This predates 0.8.0 and is identical on both paths, so it is **not** a regression of
event-driven publication — but the criterion asked, and this is the answer. The
`@app.device` archetype is unaffected: its `state_model` is threaded onto the context
(`_wiring/_context.py:120`) and `publish_state` validates directly, which is the path
jeelink2mqtt's `sensor_entity` takes. wiz2mqtt declares no `state_model` by design.
Tracked as `cap-b8h`, with the current behaviour pinned by a regression test that will
fail loudly when upstream fixes it.

### Criterion 16: both guards were lifted

The criterion asked whether the `triggerable` + `group=` and `triggerable`-on-root
registration guards still applied, or had a documented new answer. 0.8.0 lifted both, so
the new behaviour is asserted instead of the old.

- **Root entities (ADR-064, proposal open question 4).** `triggerable="local"` is now
  allowed on an unnamed entity — a local wake needs no topic segment. An MQTT source on
  a root entity is still rejected, and now at registration rather than at run.
- **Coalescing groups (ADR-067, proposal open question 6).** `triggerable=` and `group=`
  now coexist; an arm reaches the group scheduler through the group's shared wake event.
  This is not hypothetical downstream: vito2mqtt registers all seven Optolink signal
  groups `triggerable="local"` with `group="optolink"` and a `min_interval=` throttle
  (`_registration.py:71-78`).

### Open question 7: health and restart accounting

The proposal recorded this as *believed but not verified* — the runner path looked
shared, but had not been read end to end. It now has been.

`woke_by_trigger` is threaded through `_run_single_telemetry` for exactly one purpose:
`_update_trigger_kwargs` (`_runners/_telemetry_runner.py:380-385`), which injects the
`TriggerPayload` a handler may declare. Everything downstream of the handler returning —
`_execute_cycle_attempt` → `_process_cycle_result` → `_handle_telemetry_outcome` /
`_handle_telemetry_error` → `health_reporter.set_device_status` and
`_circuit_breaker_record` — receives no wake reason and cannot branch on one. The group
path (`_process_group_handler_result`) reaches the same `_handle_telemetry_outcome`.

The heartbeat that carries device status to `{prefix}/status` is published on a cadence
no unit-scale test window reaches, so the executable assertion is on the per-cycle
observable instead: three consecutive identical failures produce exactly one error
publication — the runner carries `last_error_type` across cycles and only republishes on
a change — and both the count and the payload match between a woken and a ticked entity,
as does the availability sequence.

## Two things the acceptance work turned up

Both are testing- and framework-surface findings rather than behaviour changes, and both
have beads.

- **`cap-b8h`** — telemetry `state_model=` is bypassed for a plain-dict return, as above.
- **`cap-doo`** — `AppHarness` cannot run devices and a stream together. `run()`
  unconditionally empties `app._streams` for its duration (`testing/_harness.py:207-210`)
  and `inject_stream()` reads that same list, so the two cannot drive one app at once.
  That is precisely the shape ADR-064/065 introduced — a stream handler arming an entity
  that is concurrently running its own loop. jeelink2mqtt's acceptance test works around
  it by driving the real `receiver` generator over a `DeviceContext` built from the
  harness's own doubles, using only public API; every app adopting the pattern will
  otherwise re-derive that.

## Follow-ups

| Bead      | What it takes from here                                                                 |
| --------- | ---------------------------------------------------------------------------------------- |
| `cap-b8h` | Files the `state_model=` bypass upstream; inverts the pinning test when a fix ships       |
| `cap-doo` | Files the harness limitation upstream; replaces the hand-built `DeviceContext` when fixed |
| `cap-o9x` | Collects the now five `RealSleepClock` copies into one home                               |
| `cap-9hn` | `min_interval=` values per deployment. The tests pin *which* apps carry a throttle, not the values, so that work changes one place |

`cap-rbs` needs nothing from here: ADR-005 was written from the first adoptions'
evidence in `42a5d55`, ahead of this acceptance rather than behind it, exactly as ADR-004
was for runtime discovery.
