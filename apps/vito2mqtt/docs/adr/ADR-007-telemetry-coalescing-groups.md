# ADR-007: Telemetry Coalescing Groups

## Status

Accepted **Date:** 2026-03-03 | Amended **Date:** 2026-09-02

## Context

The vito2mqtt bridge registers 7 telemetry handlers — one per signal domain
(outdoor, hot\_water, burner, heating\_radiator, heating\_floor, system,
diagnosis). Each handler polls its signals from the boiler via the Optolink
serial interface (ADR-003, ADR-004).

In the current cosalette execution model, each telemetry handler runs as an
independent `asyncio.Task` with its own sleep/execute/publish loop. When
multiple handlers share the same polling interval (6 of 7 groups default to
300 s, 1 to 3600 s per ADR-005), each opens a **separate** P300 serial session
at roughly the same wall-clock moment.

This causes several problems on a 4800-baud serial bus:

- **Session overhead** — each P300 handshake costs \~200 ms. Six separate
  sessions at t=300 spend \~1.2 s just on handshakes instead of \~0.2 s.
- **Bus contention** — rapid session cycling stresses the Vitodens controller.
- **Timing drift** — independent sleep loops drift apart because each handler
  sleeps *after* its own (varying-length) execution.
- **Scalability** — adding signal groups linearly increases session count.

The solution must work at the cosalette framework level so that other projects
with shared adapter resources (serial buses, SPI interfaces, rate-limited APIs)
benefit from the same mechanism.

### Key requirements

1. At t=0 (startup), all handlers fire in a single shared session.
2. At coinciding ticks (e.g., t=3600 where both 300 s and 3600 s intervals
   fire), handlers share one session.
3. Arbitrary intervals (300, 400, 550) must coalesce whenever they coincide.
4. The mechanism must be a framework-level feature in cosalette.
5. The user-facing API should be explicit and readable — an `group=` parameter
   on `@app.telemetry()` / `app.add_telemetry()`.

## Decision

Add **coalescing groups** to cosalette's telemetry API — a new optional
`group` parameter on `@app.telemetry()` and `app.add_telemetry()` that declares
which handlers should share execution windows when their intervals coincide.

Handlers in the same coalescing group are managed by a shared **tick-aligned
scheduler** that:

- Uses a priority queue to compute a global timeline of fire events
- Groups all handlers due at the same tick into a sequential batch
- Executes the batch in a single execution window (enabling adapter session
  sharing)
- Preserves per-handler publish strategies, error isolation, persistence, and
  init functions

Handlers without a `group` parameter (or in different groups) run independently,
preserving full backward compatibility.

### User-facing API

```python
# Decorator form
@app.telemetry(name="outdoor", interval=300, group="optolink")
async def poll_outdoor(port: OptolinkPort) -> dict[str, object]:
    ...

# Imperative form
app.add_telemetry(
    name="outdoor",
    func=handler,
    interval=300,
    group="optolink",
)
```

### vito2mqtt usage

```python
def register_telemetry(app: App) -> None:
    for group_name in SIGNAL_GROUPS:
        app.add_telemetry(
            name=group_name,
            func=_make_handler(group_name),
            interval=_get_interval(settings, group_name),
            publish=OnChange(),
            group="optolink",       # ← all share the adapter
        )
```

## Decision Drivers

- Minimize serial bus sessions for slow (4800 baud) Optolink interface
- Deterministic tick-aligned timing eliminates drift
- Explicit `group=` parameter makes coalescing visible and intentional
- Framework-level solution benefits all cosalette projects
- Backward compatible — ungrouped handlers are unaffected
- Per-handler semantics (publish strategy, error isolation, persistence)
  remain intact

## Considered Options

- **Option A: Tick-Aligned Scheduler (implicit, all handlers)** — Replace all
  independent loops with a single global scheduler. All handlers are
  automatically coalesced.
- **Option B: Adapter Keep-Alive** — Keep independent handler tasks, make the
  adapter smart enough to hold sessions open between rapid calls.
- **Option C: Coalescing Groups (explicit `group=` parameter)** — Users
  declare which handlers share execution windows via a `group` parameter.

## Decision Matrix

| Criterion                          | A: Global Scheduler | B: Keep-Alive | C: Coalescing Groups |
| ---------------------------------- | :-----------------: | :-----------: | :------------------: |
| Satisfies all 5 requirements       |          4          |       2       |          5           |
| Framework generalizability         |          5          |       1       |          4           |
| API clarity and readability        |          3          |       5       |          5           |
| Implementation complexity          |          3          |       3       |          3           |
| Deterministic timing (no drift)    |          5          |       2       |          5           |
| Backward compatibility             |          3          |       5       |          5           |
| Handles arbitrary intervals        |          5          |       3       |          5           |
| Session sharing at t=0             |          5          |       2       |          5           |
| **Total**                          |        **33**       |     **23**    |        **37**        |

_Scale: 1 (poor) to 5 (excellent)_

Option C scores highest because it combines deterministic tick-aligned
scheduling with explicit user intent. The `group=` parameter makes the
coalescing behavior readable and intentional — developers can see at a
glance which handlers share resources, which is more valuable for long-term
maintainability than implicit "magic" scheduling.

Option A was close but penalised for implicitly changing the execution model
for all handlers (reduced backward compatibility) and for hiding the
coalescing intent from the reader.

Option B was rejected because it relies on timing heuristics (idle timeouts)
that provide no guarantee of coalescing, especially at startup.

## Consequences

### Positive

- Serial sessions reduced from N (one per handler) to 1 per coinciding tick —
  e.g., 2 sessions per cycle instead of 7 for the default vito2mqtt config
- Deterministic tick alignment eliminates timing drift between grouped handlers
- Explicit `group=` parameter is self-documenting and immediately visible
  in registration code
- Full backward compatibility — existing ungrouped handlers work identically
- Per-handler semantics preserved: each handler retains its own publish
  strategy, error recovery, persistence policy, and init function
- Other cosalette projects can use coalescing groups for SPI buses,
  rate-limited APIs, or any shared-resource scenario

### Negative

- New framework concept for users to learn (mitigated by being opt-in and
  having a clear, single-parameter API)
- Scheduler adds code complexity to cosalette's core execution path
- Within a batch, handlers execute sequentially — for adapters with
  independent resources this is suboptimal (mitigated: this only affects
  handlers that *explicitly* opted into the same group)
- Floating-point tick arithmetic requires care to avoid precision issues
  (mitigated: use integer-millisecond internal representation)

## Amendment (2026-09-02) — Additive

**Rationale:** cosalette 0.8.0 (ADR-067) lifted the mutual exclusion between triggerable= and group=. Until then a coalescing-group member could not declare a trigger source at all, which is why the command path was documented as eventually consistent: after a write, the retained state topic waited for the group's next scheduled tick - up to polling_system = 3600 s for the system group, 300 s for the rest. The coalescing decision itself is unchanged and still correct; what is added is a second, event-driven entry point into the same shared scheduler, so this is recorded as an additive sub-decision rather than a correction.

### Additional Sub-Decision: Command-Triggered Wake Inside the Coalescing Group

Every `optolink` group member is additionally registered `triggerable="local"`, and a command handler calls the injected `EntityNotifier` with its own group name after a successful write.

```python
app.add_telemetry(
    name=group,
    interval=setting_ref(INTERVAL_ATTR[group]),
    group="optolink",
    triggerable="local",
    min_interval=COMMAND_WAKE_MIN_INTERVAL_SECONDS,
    ...
)
```

**Bus exclusion is preserved.** The arm does not start a task of its own. cosalette's group scheduler races the group's tick deadline against its members' arms; a woken member is merged into the group's next batch (`batch = sorted(set(due) | released)`), so it still runs inside the one shared P300 session this ADR exists to guarantee. Requirements 1-3 of this ADR are untouched: the wake adds a fire event to the shared timeline, it does not bypass it.

**`triggerable="local"` adds no public surface.** Unlike `triggerable=True` (MQTT), a local source subscribes no `/set` topic. The only arming path is the in-process notifier call in `devices/commands.py`; the MQTT topic layout of ADR-002 is unchanged.

**Why every group, not only the four writable ones.** `COMMAND_GROUPS` is a subset of `SIGNAL_GROUPS`, and `EntityNotifier` raises `UnknownEntityError` at *call* time for a name that declares no local source. Registering all seven uniformly costs one trigger slot each and removes a class of latent runtime error if a group later becomes writable.

### Additional Sub-Decision: Storm Throttle Sized to the Serial Bus

`min_interval=COMMAND_WAKE_MIN_INTERVAL_SECONDS` (15 s) bounds the spacing between two *trigger-initiated* runs of a member (cosalette ADR-066). It is not decoration: a full weekly timer schedule is written as seven separate `/set` payloads, and without a floor each would queue a full group read on a 4800-baud bus.

The throttle is enforced on the consuming end, never on the arm, so the notifier call from the command handler stays non-blocking. An arm landing inside a closed window is *held*, not dropped - the last write of a burst is still reflected once the window reopens. The `interval=` heartbeat is unaffected in both directions: it neither postpones the window nor is postponed by it.

15 s sits well below the shortest poll interval (300 s), so the throttle bounds bursts without becoming the effective floor for a single write.

### Additional Sub-Decision: Acceleration, Not Confirmation

A group's command signals and its telemetry signals are disjoint - the intersection of `COMMAND_GROUPS[g]` and `SIGNAL_GROUPS[g]` is empty for all four writable groups. Writing `heating_curve_gradient_m1` does not put that value on `heating_radiator/state`; it changes what the Vitotronic subsequently reports for `flow_temperature_setpoint_m1`.

The wake therefore accelerates the pickup of the boiler's *reaction*, and the eventual-consistency model of the command path is narrowed rather than replaced: state is still published by telemetry, never by command confirmation. Where the boiler has not yet reacted when the woken read runs, `OnChange()` gates the publish and the `interval=` heartbeat remains the backstop. Only a write that actually reached the bus wakes - a payload fully suppressed by the read-before-write guard changes nothing and arms nothing.

### Additional Positive Consequences

- A command write is reflected in the retained state topic within seconds of the boiler reacting, instead of waiting up to a full poll interval - 3600 s for the system group under the ADR-005 defaults
- The `interval=` setting becomes a heartbeat and staleness bound rather than the sole determinant of command feedback latency, so poll intervals can be tuned for bus load without trading away responsiveness
- The wake path reuses the group's existing scheduler, publish strategy, error isolation and persistence unchanged - a woken run is indistinguishable downstream from a ticked one

### Additional Negative Consequences

- A second entry point into the group scheduler: reasoning about when a group runs now requires reading both the interval and the command path, where before the interval alone was sufficient
- `min_interval=` is a third timing constant alongside the per-group poll intervals, and unlike them it is a module constant rather than a setting - tuning it for an unusually slow bus needs a code change
- The command handler now depends on the ADR-002 invariant that every command group name is also a telemetry entity name; violating it produces an `UnknownEntityError` at write time rather than at registration, which is why an integration test asserts it per group
