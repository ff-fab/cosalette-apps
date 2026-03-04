# Command Handlers Design — Writable Parameters

## Context

The telemetry layer (read side) is complete: 7 signal groups poll the boiler via
`OptolinkPort.read_signals()` and publish to `{prefix}/{device_id}/{group}/state`.

The write side needs command handlers that subscribe to
`{prefix}/{device_id}/{group}/set` topics and dispatch `write_signal()` calls via
the same `OptolinkPort` protocol. ADR-002 defines 4 domains with writable parameters:

| Domain              | Writable signals | Types             |
|---------------------|------------------| ------------------|
| `hot_water`         | 9                | IUNON, CT         |
| `heating_radiator`  | 13               | IS10, IUNON, BA, CT |
| `heating_floor`     | 13               | IS10, IUNON, BA, CT |
| `system`            | 8                | TI, CT            |

Total: 43 writable commands.

## Option A: Declarative Registry + Generic Handler Factory (Recommended)

Mirror the telemetry pattern: define a `COMMAND_GROUPS` registry mapping group names →
writable signal tuples, then use a factory `_make_command_handler(group)` that returns
an async handler accepting `payload: bytes` and `port: OptolinkPort`.

```python
COMMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "hot_water": ("hot_water_setpoint", "hot_water_pump_overrun", "timer_hw_monday", ...),
    "heating_radiator": ("heating_curve_gradient_m1", ..., "timer_m1_monday", ...),
    "heating_floor": ("heating_curve_gradient_m2", ..., "timer_m2_monday", ...),
    "system": ("system_time", "timer_cp_monday", ...),
}
```

The generic handler:

1. Parses `payload` (bytes → JSON dict)
2. Validates each key is in the group's allowed signals
3. Writes each signal via `port.write_signal(name, value)`
4. Returns `None` (no auto-state-publish; telemetry handles state)

**Advantages:**

- Consistent with the telemetry pattern — same declarative, data-driven approach
- Single handler factory eliminates code duplication across 4 domains
- Adding signals is a data change, not a code change (Open/Closed Principle)
- Easily testable: one parametrized test suite covers all groups

**Disadvantages:**

- Slightly less explicit per domain (all grouped in a registry)
- Domain-specific validation (e.g., value ranges) would need extension later

## Option B: Per-Domain Handler Functions

Write separate `_handle_hot_water()`, `_handle_heating_radiator()`, etc. functions
with hard-coded signal lists and per-domain validation logic.

**Advantages:**

- More explicit per domain
- Easier to add per-domain validation logic later

**Disadvantages:**

- Significant code duplication (4 handlers doing the same parse → validate → write)
- More maintenance burden when signals change
- Violates DRY

## Recommendation

**Option A.** The generic factory pattern mirrors the established telemetry pattern,
keeps the codebase consistent, and the Open/Closed Principle means adding or moving
signals requires only data changes. Per-domain validation can be layered on top later
via a validation dispatch table if needed.

## Design Details

### Module: `packages/src/vito2mqtt/devices/commands.py`

New module parallel to `telemetry.py`:

```python
# Public API
def register_commands(app: App) -> None:
    """Register command handlers for all writable signal groups."""

# Data registry
COMMAND_GROUPS: dict[str, tuple[str, ...]] = { ... }

# Error types (reuse from errors.py)
# - InvalidSignalError: signal not in group
# - CommandNotWritableError: already validated by adapter, but belt-and-suspenders
# - json.JSONDecodeError: malformed payload
```

### Payload Contract

MQTT messages arrive as `payload: bytes`. The handler:

1. Decodes UTF-8, parses JSON → `dict[str, Any]`
2. Validates every key is in the group's `COMMAND_GROUPS[group]`
3. Skips empty payloads (no-op, returns `None`)
4. Writes signals sequentially via `port.write_signal()`
5. Returns `None` — state is published by telemetry polling, not by command
   confirmation (eventual consistency model)

Unknown keys raise `InvalidSignalError` to notify the caller.

### Registration Pattern

```python
def register_commands(app: App) -> None:
    settings = app.settings  # validate type
    for group_name in COMMAND_GROUPS:
        app.add_command(
            name=group_name,
            func=_make_handler(group_name),
        )
```

### Error Handling

Errors from `port.write_signal()` propagate to cosalette's error publisher
(configured via `error_type_map`). The handler does NOT catch adapter errors —
cosalette handles per-handler error isolation.

### Tests: `packages/tests/unit/devices/test_commands.py`

Parallel structure to `test_telemetry.py`:

1. **Registration tests** — `register_commands` calls `add_command` for each group
2. **Handler tests** — parametrized across groups, verify `write_signal` dispatch
3. **Validation tests** — unknown keys, empty payload, malformed JSON
4. **Error propagation** — adapter errors bubble through
5. **Cross-reference** — every writable signal is covered by exactly one group

## Summary and Next Steps

1. Create `COMMAND_GROUPS` registry in `devices/__init__.py`
2. Implement `devices/commands.py` with `register_commands()` + factory
3. Write comprehensive tests in `tests/unit/devices/test_commands.py`
4. Run quality gates
