---
status: Accepted
date: 2026-09-05
impact: moderate
tags: [telemetry, serialization, dependencies, architecture]
---

# ADR-007: cosalette 0.9.0 state_model Enforcement Adoption

## Status

Accepted **Date:** 2026-09-05

## Context

cosalette 0.9.0 (upstream ADR-068) makes `state_model=` unconditional. On `@app.telemetry` and `@app.command`, the handler return value is now validated against the declared model on every cycle, and `state_model=` outranks the return annotation: when a handler declares `state_model=M` alongside a return annotation naming a different type, `state_model` wins and registration emits a `UserWarning` naming both. Every app in this monorepo and the workspace root set `filterwarnings = ["error"]` in their pytest config, so that warning became a collection error the moment the pin moved to `>=0.9.0,<0.10`.

Five handler registrations tripped it, all telemetry: airthings2mqtt `_telemetry`, caldates2mqtt `calendar`, gas2mqtt `gas_counter` and `temperature`, and vito2mqtt's `make_telemetry_handler` factory — one function that backs all seven `group="optolink"` signal groups. Each already declared `state_model=<Reading model>` as the typed wire contract and, separately, carried a loose `-> dict[str, object]` (or `-> dict[str, object] | None`) return annotation left over from before typed contracts existed. The two never disagreed in behaviour — the models are the real contract — but 0.9.0 makes the mismatch a hard error.

0.9.0 also changed serialization: a validated payload is dumped with `exclude_none=True` (ADR-068 clause C/D), so an absent optional field becomes an omitted key rather than an explicit `null`. This was audited across every state model in the monorepo and nothing moved on the wire: gas2mqtt's `build_state` already omitted `consumption_m3` conditionally, wallpanel-control returns model instances that take the serialise fast path where `exclude_none` does not apply, and the jeelink2mqtt, velux2mqtt and vito2mqtt models carry no optional fields. All nine apps report `drift_count: 0` on the new retained `{prefix}/_meta/state_model_drift` snapshot (upstream ADR-069), which publishes exactly this declaration-conflict information for a whole broker.

The upgrade landed in PR #228 on `chore/cosalette-0.9.0`. How the five mismatches were resolved is not self-evident from that diff and it constrains every app, so it is recorded here at monorepo scope, exactly as ADR-004 and ADR-005 recorded their framework adoptions.

## Decision

Use the upstream 0.9.0 migration path for the `state_model=`/annotation conflict: drop the contradicting `-> dict[str, object]` return annotations from the five affected telemetry handlers and let `state_model=` stand as the sole return contract. Do not suppress the warning, and do not rewrite the handlers to construct and return model instances under a `-> M` annotation as part of this upgrade — that larger change is the better end state and is filed separately as cap-z02.

```python
# before — two return-contract declarations; a hard error under cosalette 0.9.0
app.add_telemetry(name="gas_counter", state_model=GasCounterReading, ...)(gas_counter)

async def gas_counter(...) -> dict[str, object] | None:
    ...

# after — state_model= is the sole contract, handler body untouched
async def gas_counter(...):
    ...
```

## Decision Drivers

- The upstream 0.9.0 migration note prescribes exactly this: when `state_model=` and the return annotation disagree, drop the annotation and keep `state_model=`.
- A breaking dependency bump should have the smallest defensible blast radius — no handler body should change, so no behaviour can change beyond the pin itself.
- Two contradicting return-contract declarations are the actual defect; `state_model=` should be the single source of truth for the wire shape.
- The genuinely better end state — handlers returning validated model instances under a `-> M` annotation — is a much larger change with its own payload-shape risk, and is better done deliberately (cap-z02) than bundled into an upgrade.
- Declaration drift is now runtime-observable: `{prefix}/_meta/state_model_drift` gives the repo a machine-checkable invariant, `drift_count == 0`.

## Considered Options

### Option 1: Drop the return annotations (chosen)

Remove the `-> dict[str, object]` / `-> dict[str, object] | None` annotation from each of the five handlers. `state_model=` stays and is the only declared return contract. No handler body changes; the diff is five signature lines.

- *Advantages:* Smallest possible change for a breaking dependency bump — no handler logic is touched, so nothing can regress beyond the pin.; Exactly the path the upstream 0.9.0 migration note prescribes, so a later `cosalette ai init` refresh will not fight it.; Removes the real defect — two return-contract declarations that could drift apart — leaving `state_model=` as the unambiguous source of truth.; `drift_count: 0` on `{prefix}/_meta/state_model_drift` becomes a true, machine-checkable invariant for the whole repo.
- *Disadvantages:* Five handlers end up with no return annotation at all — a genuine typing regression that neither ruff (no `ANN` rules selected) nor ty flags or requires.; The wire contract for these entities is now discoverable only at the registration call site (`state_model=…`), not from the handler signature a reader lands on first.; `make_telemetry_handler`'s inner function becomes a bare `async def handler(port):` — the least informative signature of the five.

### Option 2: Return model instances

Annotate each handler `-> <Reading model>` and change its body to construct and return an instance of that model instead of a dict. Annotation and `state_model=` then agree and both document the contract.

- *Advantages:* Best end state: the contract is stated at the signature and at registration, and the two cannot drift.; Restores full type-checker coverage of the return path — a wrong field name or type is caught statically.; Moves the repo onto the typed-contract path upstream is steering toward.
- *Disadvantages:* Every one of the five handlers (vito2mqtt's backs seven groups) gets a body rewrite — a much larger diff riding on a breaking dependency bump.; Hand-constructing each model introduces its own payload-shape risk: a mistyped field or wrong default would change the wire output, the exact thing the annotation drop avoids.; Larger review surface and more merge-conflict exposure while the upgrade is in flight, for no wire-visible benefit today.

### Option 3: Drop state_model=, keep the annotations

Delete the `state_model=` keyword from the five registrations and keep the existing `-> dict[str, object]` annotations. The mismatch disappears because only one declaration remains — at the cost of runtime return validation and `exclude_none` normalization on those entities.

- *Advantages:* Also a five-line diff, and it keeps a return annotation on every handler.; Introduces no `exclude_none=True` normalization, so there is provably zero wire change.
- *Disadvantages:* Throws away runtime payload validation on ten-plus telemetry entities to settle a declaration conflict — solving the wrong problem.; Regresses off the typed-contract path; `-> dict[str, object]` is a non-contract that tools cannot check against anything.; The retained `{prefix}/_meta/state_model_drift` snapshot would still show these entities as untyped, inviting the same question again next release.; Diverges from the upstream migration guidance, so future refreshes and downstream acceptance tests would need carve-outs.

## Decision Matrix

| Criterion | Drop the return annotations | Return model instances | Drop state_model=, keep the annotations |
| --- | --- | --- | --- |
| Blast radius of the dependency bump (5 = smallest diff, no behaviour change) | 5 | 2 | 4 |
| `state_model=` as the single source of truth for the wire contract | 4 | 5 | 2 |
| Type-checker visibility of the return type at the handler | 1 | 5 | 3 |
| Freedom from payload-shape regression risk in this change | 5 | 3 | 5 |
| Alignment with the upstream-prescribed 0.9.0 migration path | 5 | 4 | 2 |

_Scale: 1 (poor) to 5 (excellent)_

## Consequences

### Positive

- One return contract per entity: `state_model=` alone, with no contradictory annotation for a reader or a tool to reconcile.
- Zero payload change, and it is audited: all nine apps publish `drift_count: 0` on `{prefix}/_meta/state_model_drift`, and the `exclude_none=True` dump (ADR-068 clause C/D) changes nothing on the wire — gas2mqtt already omitted `consumption_m3` conditionally, wallpanel-control returns model instances on the serialise fast path, and the jeelink2mqtt, velux2mqtt and vito2mqtt models have no optional fields.
- Smallest possible diff for a breaking dependency bump — no handler body is touched.
- The declaration conflict is now a runtime-observable invariant (`drift_count == 0`), not something visible only in a careful reading of each composition root.
- Follows the upstream-prescribed migration path, so a future `cosalette ai init` refresh and the downstream acceptance suites will not need carve-outs for these handlers.

### Negative

- Five telemetry handlers now carry no return annotation at all — a real typing regression that neither ruff (no `ANN` rules selected) nor ty flags or requires. `make_telemetry_handler`'s inner function is the worst case: a bare `async def handler(port):`.
- The wire contract for these entities is discoverable only at the registration site (`state_model=…`), not from the handler signature.
- The better end state — handlers returning validated model instances — is deferred to cap-z02, so the repo sits in an interim shape until that lands.
- `exclude_none=True` now governs null-vs-absent behaviour for these payloads' optional fields. It is a no-op today, but any optional field later added to one of these models will be omitted-when-`None` rather than sent as explicit `null` — a wire-behaviour change a future author must anticipate.

_2026-09-05_
