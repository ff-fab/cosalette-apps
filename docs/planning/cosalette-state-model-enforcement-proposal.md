# Enhancement Proposal: make `state_model=` mean what the docs say it means

**Status:** proposed — upstream ask against cosalette; no downstream fix worth building
**Raised by:** cosalette-apps, out of the `cap-8au` acceptance work (criterion 8 of
[the event-driven publication proposal](cosalette-event-driven-publication-proposal.md))
**Verified against:** cosalette 0.8.0 and pydantic 2.12.5, both the installed wheels,
source read directly (`_runners/_contracts.py`, `_runners/_telemetry_runner.py`,
`_runners/_command_runner.py`, `_wiring/_context.py`,
`_ai_content/_help_extra.py`) plus live reproduction against the ten affected
registrations in this monorepo **Implementation lands:** in the cosalette framework
repository, **not here**. Nothing downstream changes before a release carries the fix.
**Tracking bead:** `cap-b8h`

## Summary

`state_model=` does not validate anything on `@app.telemetry` or `@app.command` in the
common case. Two independent mechanisms defeat it, and the shipped guidance promises the
opposite in as many words. Ten of the twelve `state_model=` declarations on
value-returning handlers in this monorepo are runtime no-ops today; their authors
believe otherwise.

The fix is small in code and non-trivial in payload shape, so this proposes a staged
rollout rather than a straight behaviour change.

## Context

`cosalette ai help` ships this rule (`_ai_content/_help_extra.py:396-401`), verbatim:

> One rule for state_model: if you declare it, published state is validated. Since 0.6.0
> that holds on **every** publishing archetype — `@app.telemetry` and `@app.command`
> validate the handler return value, `@app.device` and `@app.stream` validate every
> `ctx.publish_state()` payload. Omit state_model (the default) and no validation happens
> at all.

The `@app.device` / `@app.stream` half is true. Their `state_model` is threaded onto the
`DeviceContext` (`_wiring/_context.py:120`) and `publish_state` routes through
`validate_published_state` (`_contracts.py:336+`), which calls
`TypeAdapter.validate_python` directly. That path is correct and this proposal does not
touch it.

The `@app.telemetry` / `@app.command` half is not true. Both route their return value
through `normalize_handler_return` (`_telemetry_runner.py:65`, `_command_runner.py:273`),
and two things there defeat the declaration.

## Defect 1 — a return annotation silently outranks `state_model=`

`normalize_handler_return` (`_contracts.py:444`):

```python
annotation = get_return_annotation(func) or state_model
return normalize_return(value, annotation, handler=handler_name)
```

`state_model` is a *fallback for handlers with no return annotation*, not a contract. A
handler that annotates its return — which every type-checked codebase does — never
consults its own declared model. And the annotation people write for a heterogeneous
payload is `dict[str, object]`, whose `TypeAdapter` accepts literally anything.

This is the dominant idiom, not a corner case. Every `state_model=` on a value-returning
handler in this monorepo, read off the live `App` objects:

| App               | Registration                                | `state_model=`       | Return annotation         | Validates? |
| ----------------- | ------------------------------------------- | -------------------- | ------------------------- | ---------- |
| airthings2mqtt    | `airthings`                                 | `AirthingsReading`   | `dict[str, object]`       | **no**     |
| caldates2mqtt     | `calendar`                                  | `CalendarState`      | `dict[str, object]`       | **no**     |
| gas2mqtt          | `gas_counter`                               | `GasCounterReading`  | `dict[str, object] \| None` | **no**   |
| gas2mqtt          | `temperature`                               | `TemperatureReading` | `dict[str, object]`       | **no**     |
| vito2mqtt         | seven Optolink groups (`outdoor` … `diagnosis`) | seven models     | `dict[str, object]`       | **no**     |
| wallpanel-control | `display`, `system/action`                  | `DisplayState`, `SystemActionState` | the same models | yes |

Ten of twelve are inert. They still drive schema generation and AsyncAPI, so nothing
looks wrong from the outside — which is exactly why this survived to 0.8.0.

The two that work do so by accident of style: those handlers return a model *instance*
and annotate it, so the annotation happens to be the model.

## Defect 2 — the EAFP fast path swallows a mismatch

Even when the model *is* the effective annotation, a handler returning a plain `dict`
is not validated. `normalize_return` (`_contracts.py:288-296`):

```python
try:
    normalised = adapter.dump_python(value, mode="json")
except Exception:
    validated = adapter.validate_python(value)
    normalised = adapter.dump_python(validated, mode="json")
```

The comment explains the design — an EAFP path that is free for already-valid instances
and, unlike the `isinstance` check it replaced, works for PEP 585/604 generics. The
premise is that an invalid value makes Pydantic raise. It does not: serialising a plain
`dict` against a `BaseModel` adapter emits `PydanticSerializationUnexpectedValue` as a
`UserWarning` and returns the input unchanged. The fallback never runs.

Reproduced against the shipped wheels — a handler declaring `reading: int` and returning
`{"reading": "not-an-int"}` publishes `{"reading":"not-an-int"}` to its retained state
topic with no error:

```text
dump_python(bad)                     -> {'reading': 'not-an-int'}   warnings=['UserWarning']
dump_python(bad, warnings='error')   -> RAISED PydanticSerializationError
validate_python(bad)                 -> RAISED ValidationError
```

Validation does engage when the value cannot be serialised at all (`{"reading": object()}`
raises, falls through, and publishes `ReturnValidationError` to `{prefix}/{name}/error`),
which is why the hole is invisible to a test suite that only exercises hard failures.

## Proposed change

Three parts. The first two are the fix; the third is a decision the first two force.

### 1. Let the explicit declaration win

```python
annotation = state_model or get_return_annotation(func)
```

One line, and it makes telemetry and commands consistent with devices and streams, where
a declared `state_model` already wins regardless of what the handler is annotated as.
`state_model=` is an opt-in contract; a return annotation is frequently written to
satisfy a type checker. The explicit knob should not lose to the incidental one.

### 2. Make the fast path fail when it should

```python
normalised = adapter.dump_python(value, mode="json", warnings="error")
```

`warnings="error"` turns `PydanticSerializationUnexpectedValue` into
`PydanticSerializationError`, which the existing `except Exception:` already catches, so
the existing `validate_python` fallback does the rest. The fast path stays free for
genuinely valid instances — a real `BaseModel`, dataclass or TypedDict dumps with no
warning and no extra work. No new dependency, no new branch.

### 3. Decide what validated serialisation emits

This is the part that costs something, and it needs an explicit answer rather than a
default. Once validation actually runs, `dump_python` on the validated model reshapes the
payload:

```text
handler returns {"state": "ON"}         # brightness genuinely unknown

today                    -> {'state': 'ON'}
fixed, naive             -> {'state': 'ON', 'brightness': None, 'color_temp': None}
fixed, exclude_none=True -> {'state': 'ON'}
fixed, exclude_unset=True-> {'state': 'ON'}
```

Null-filling absent optional fields is a visible change to retained topics and to Home
Assistant `value_template`s reading them. This repo already has an app that refused
`state_model=` for exactly this reason — wiz2mqtt's `bulb_entity` carries the comment
*"the payload's keys are conditionally present, which a Pydantic `state_model` would
force to null-fill on every publish rather than omit"*. That workaround exists because
the framework has no stated answer here.

Recommendation: serialise with `exclude_none=True`, so enforcement preserves the shape
apps publish today and the conditional-key idiom stops needing a workaround. Extra keys
not on the model are dropped either way — that is validation working, and it is the one
change that should be loud.

Worth noting for scale: all ten affected models in this monorepo are **dataclasses**, and
exactly one field across all ten carries a default. Null-filling is therefore not the
dominant local risk — a missing *required* field is. That is a `ValidationError` rather
than a reshaped payload, which is louder and more correct, but it is also the failure most
likely to surface on the first boot after enforcement.

## Alternatives

| Alternative                                          | Why it loses                                                                                                                                                                 |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Fix the documentation instead of the code            | Cheapest, and it is the honest fallback if enforcement is rejected. But `state_model=` then has no runtime meaning on two of four archetypes while carrying a name that says it does; it becomes schema metadata with a misleading spelling |
| Fix defect 2 only                                    | Changes nothing for ten of the twelve registrations here. The annotation still outranks the model, so the declaration stays inert wherever a return annotation exists — which is everywhere |
| Fix defect 1 only                                    | Closes the common case, but leaves a handler that annotates `-> Model` and returns a `dict` unvalidated. Both mechanisms have to go or the rule still has an exception nobody can predict |
| Reject a registration declaring both `state_model=` and a return annotation | Loud, cheap, no silent behaviour change — and it fails ten existing registrations at startup on upgrade. A warning buys the same information without the outage |
| Validate against both, annotation for serialisation  | Two adapter passes per cycle on the hot path, to express a disagreement that should be a registration error rather than a runtime merge                                        |

## Migration

Enforcement will publish `ReturnValidationError` for handlers whose payloads never
matched their declared models — which is the point, but not something to spring on a
running deployment.

1. **Phase 1 — detect, in a minor release.** Apply defect 1's precedence and defect 2's
   `warnings="error"` in a *dry* mode: on mismatch, log once per registration at WARNING
   naming the handler, the model and the offending field paths, then publish exactly what
   is published today. Every downstream gets its list from one boot, with no behaviour
   change and nothing to opt into. The list is the migration: a model that has been wrong
   since it was written is more likely than a handler that regressed.
2. **Phase 2 — enforce, in the next minor.** Same code paths, mismatches now raise. The
   Phase 1 warning text should name the release that will start enforcing.

An `App(strict_state_models=...)` flag could bridge the two for anyone who wants
enforcement immediately, but it should not become the long-term interface — the
documented rule is unconditional and the implementation should be too.

## Validation criteria

"Fixed" means the following hold. Numbered for the same reason the previous proposal's
were: so the answers can be checked off one at a time.

1. A `@app.telemetry` handler declaring `state_model=M` and annotated `-> dict[str, object]`
   validates its return value against `M`.
2. The same holds for `@app.command`.
3. A handler returning a plain `dict` that does not conform raises `ReturnValidationError`
   and publishes to `{prefix}/{name}/error`, with no publish to the state topic.
4. A handler returning a conforming plain `dict` publishes successfully, and the published
   payload is byte-identical to what 0.8.0 publishes for it today (this is criterion 3's
   negative control, and the whole of the compatibility promise).
5. A handler returning a valid model instance takes the fast path — asserted as no
   `validate_python` call, not as a timing measurement.
6. Absent optional fields do not appear as `null` in the published payload.
7. Extra keys not on the model are dropped, and that is asserted rather than incidental.
8. `@app.device` and `@app.stream` behaviour is unchanged, byte-for-byte —
   `validate_published_state` is not on this path and must not move.
9. A handler with no `state_model=` is unchanged, whatever its return annotation.
10. Phase 1 emits exactly one warning per affected registration per boot, not one per cycle.

## Open questions

1. **Does `state_model=` win over a *model* return annotation?** The proposal says yes
   (explicit beats incidental), but `-> ModelA` with `state_model=ModelB` is a
   contradiction that probably deserves a registration-time error rather than a silent
   winner. Not decided here.
2. **Should `exclude_none=True` apply to the device/stream path too?** It does not today,
   and this proposal deliberately leaves that path alone — but the inconsistency will be
   visible the moment someone moves a handler between archetypes.
3. **Is `warnings="error"` stable API?** It is documented on `TypeAdapter.dump_python` in
   pydantic 2.x and verified on 2.12.5. Whether cosalette wants to pin a floor for it is
   a maintainer call.
4. **Do any downstream apps publish payloads their models would reject?** Unknown, and
   not answerable by inspection — a handler builds its dict at runtime. This is precisely
   what Phase 1 exists to measure, here as much as anywhere.

## What this repo will do

Nothing until a release carries the change. `cap-b8h` holds the downstream work and
closes when the pin moves. The current behaviour is pinned by
`packages/tests/unit/test_event_driven_acceptance.py::TestParity::test_a_dict_return_bypasses_the_declared_state_model`,
which asserts the bypass in the direction that holds today and will fail loudly on the
release that fixes it — at which point it gets inverted rather than deleted, so the
contract stays asserted in whichever direction is true.
