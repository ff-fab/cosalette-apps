# cosalette Framework Enhancement: Stream Runtime Parity for Stateful Receivers

**Date:** 2026-05-06
**Author:** jeelink2mqtt maintainer
**Status:** Proposal — awaiting framework review
**Blocked work:** cap-5xy (final open child of cap-v6y)
**Superseded by:** Implementation of `AsyncStreamablePort[T]`, `DeviceContext`/`DeviceStore` injection for `@app.stream`, and `AppHarness.inject_stream` parity in cosalette (tracked in cap-5xy)

---

## Executive Summary

The jeelink2mqtt migration to `@app.stream` (cap-5xy) cannot proceed because the current cosalette 0.3.13 stream runtime lacks essential capabilities that `@app.device` handlers take for granted. Specifically, stream handlers cannot inject `DeviceContext` or `DeviceStore`, there is no clear single-source lifecycle model when the same adapter is both the stream source and the app-specific port, and the `StreamablePort[T]` protocol requires synchronous lifecycle methods that conflict with the async lifecycle already implemented in jeelink2mqtt's ports.

This proposal recommends extending the framework's `@app.stream` runtime to achieve parity with `@app.device` for dependency injection, persistence, and adapter lifecycle management. Until this enhancement lands, jeelink2mqtt should remain on the current `@app.device` receiver implementation.

---

## Expectation vs. Current Behavior

The expectations below are derived from P2 in [cosalette-framework-enhancement-proposals.md](cosalette-framework-enhancement-proposals.md).

| Aspect | Expected | Current (cosalette 0.3.13) | Impact |
|--------|---------|---------|--------|
| **DeviceContext injection** | Stream handlers can inject `DeviceContext` to publish telemetry, state, and availability | Not available. `start_stream_tasks` provider map includes settings, adapters, state, ClockPort, Logger, but not `DeviceContext` | Cannot publish raw frames, calibrated state, mapping events, or availability from stream handler |
| **DeviceStore injection** | Stream handlers can inject `DeviceStore` to restore and persist registry state | Not available. Provider map does not include `DeviceStore` | Cannot restore sensor registry on startup or persist mapping changes |
| **Async adapter lifecycle** | `@app.stream` runtime calls async lifecycle methods (`await port.start_scan()`, `await port.stop_scan()`, `await port.close()`) | `_stream_runner.run_stream` calls synchronous lifecycle: `port.open()`, `port.register_callback(...)`, `port.start_scan()`, then registers sync callbacks for stop/close via `_safe_call` | Sync cleanup callbacks silently discard the coroutines returned by `JeeLinkPort`'s async lifecycle methods — serial port never closed on shutdown (resource leak). Also forces duplicate sync/async lifecycle plumbing. |
| **Adapter access for non-stream ops** | Handler can inject concrete adapter type (e.g., `JeeLinkPort`) for operations like `jeelink.set_led(...)` while framework owns lifecycle via `StreamablePort[T]` registration | Two blockers: (1) `_validate_stream_signature` → `_find_compatible_stream_adapter` looks for a `StreamablePort[SensorReading]`-keyed adapter; jeelink2mqtt registers under `JeeLinkPort`, so `@app.stream` raises `TypeError` at decoration time before any signature check runs. (2) Even after registration is resolved, `_check_no_port_in_signature` forbids `StreamablePort[T]` parameters while the framework lacks a clear single-source lifecycle model. | `@app.stream` raises `TypeError` at decoration time (not runtime). Migration must include re-registering the adapter under `AsyncStreamablePort[SensorReading]` key. |
| **AppHarness parity** | `AppHarness.inject_stream` provides production-equivalent stream DI (DeviceContext, DeviceStore, settings, state, adapters) | `inject_stream` builds limited provider map: settings, state overrides, ClockPort, Logger. No `DeviceContext`, `DeviceStore`, or adapter providers | Integration tests cannot verify publishing, persistence, or full adapter interaction |

---

## Why This Blocks jeelink2mqtt

The cap-5xy acceptance criteria require:

1. **Receiver uses the framework stream feature** - implies `@app.stream` decorator and framework-managed lifecycle.
2. **Adapter lifecycle is framework-managed** - implies port lifecycle methods called by the stream runtime, not by application code.
3. **main.py is close to [jeelink2mqtt-main-simplification.md](jeelink2mqtt-main-simplification.md)** - implies a concise handler without explicit context manager or iterator boilerplate.
4. **Integration tests prove raw publishing, registry routing, mapping persistence, staleness, heartbeat, and shutdown behavior** - implies `AppHarness.inject_stream` can inject `DeviceContext` and `DeviceStore`.

The current `@app.device` receiver in jeelink2mqtt satisfies all integration test requirements because:

- It injects `DeviceContext` via the `@app.device` runtime
- It injects `DeviceStore` via the `@app.device` runtime
- It uses `JeeLinkPort` as an async context manager / async iterator, which encapsulates lifecycle and provides `set_led` access
- It publishes raw frames, calibrated state, mapping events, staleness, heartbeat, and availability to MQTT via `DeviceContext`

Moving to `@app.stream` would require abandoning these capabilities unless the framework extends the stream runtime to support:

- `DeviceContext` in the provider map
- `DeviceStore` in the provider map
- Async lifecycle methods in `StreamablePort[T]` or an alternate adapter protocol
- Injection of the concrete adapter type (e.g., `JeeLinkPort`) for non-stream operations, even when `StreamablePort[T]` is registered for lifecycle ownership

Without these extensions, the migration cannot proceed without either:

- Reimplementing essential features (publishing, persistence) outside the framework, or
- Staying on `@app.device` until the framework supports these capabilities

---

## Proposed Solution

### Option A: Make `@app.stream` a Device-Equivalent Runtime for DI and Persistence

**Recommendation:** Extend the cosalette framework to support the following enhancements in the `@app.stream` runtime.

#### Desired Handler Shape

```python
@app.stream(summary="JeeLink LaCrosse serial receiver")
async def receiver(
    ctx: cosalette.DeviceContext,
    stream: cosalette.Stream[SensorReading],
    jeelink: JeeLinkPort,
    store: DeviceStore,
    settings: Jeelink2MqttSettings,
    state: SharedState,
) -> None:
    """Stateful LaCrosse receiver with registry persistence and raw publishing."""
    # Restore persisted registry state before loop
    state.restore_from(store, settings)

    last_persist_time = datetime.now(UTC)

    try:
        async for reading in stream:
            now = datetime.now(UTC)  # single clock read per iteration

            # 1. Raw diagnostic (every frame, non-retained)
            # _receiver.*: module-level helpers in jeelink2mqtt/_receiver.py
            await _receiver._publish_raw(ctx, reading)

            # 2. Route through registry
            name = state.registry.record_reading(reading)

            # 3. Mapped -> filter -> calibrate -> publish
            if name is not None:
                config = state.sensor_configs.get(name)
                if config is not None:
                    calibrated = state.apply_pipeline(reading, config)
                    await _receiver._publish_sensor(ctx, name, calibrated)
                    state.record_published_reading(name, calibrated, now)
                    # Publish availability only on offline→online transition
                    if not state.is_available(name):
                        state.mark_available(name)
                        await ctx.publish(f"{name}/availability", "online", retain=True)

            # 4. Mapping events (publish state when something changed)
            if await state.flush_events(ctx, store):
                last_persist_time = now

            # 5. Periodic persistence for last_seen metadata
            new_persist_time = state.persist_registry_if_due(
                store, now, last_persist_time, 60
            )
            if new_persist_time is not None:
                last_persist_time = new_persist_time

    finally:
        # Publish all offline statuses concurrently
        await asyncio.gather(
            *[ctx.publish(f"{s.name}/availability", "offline", retain=True) for s in settings.sensors]
        )
```

Note: The concrete adapter `jeelink: JeeLinkPort` is shown as injectable for non-stream operations (e.g., `jeelink.set_led(enabled)` for LED control), but the framework must clarify lifecycle ownership to avoid handlers calling lifecycle methods.

#### DeviceContext and DeviceStore Injection for Streams

Extend the stream runtime (in `cosalette._wiring._task_lifecycle.start_stream_tasks`) to inject `DeviceContext` and `DeviceStore` into the provider map, similar to how `@app.device` handlers receive them. This enables:

- Publishing telemetry, state, and availability to MQTT via `ctx.publish(...)`
- Creating/loading a per-stream DeviceStore before handler execution
- Saving dirty store on shutdown (matching `@app.device` parity)

**Framework changes:**

1. Add `DeviceContext` to the provider map in `start_stream_tasks`
2. Add `DeviceStore` to the provider map in `start_stream_tasks` (create/load before handler, save on shutdown)
3. Update `AppHarness.inject_stream` to provide `DeviceContext` and `DeviceStore` (with mock or real implementations), achieving parity with production stream execution

#### Async Stream Source Lifecycle

Extend `StreamablePort[T]` or introduce an `AsyncStreamablePort[T]` protocol with async lifecycle methods:

```python
class AsyncStreamablePort(Protocol[T]):
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def start_scan(self) -> None: ...
    async def stop_scan(self) -> None: ...
    def register_callback(self, callback: Callable[[T], None]) -> None: ...
```

Update the stream runner (in `cosalette._runners._stream_runner.run_stream`) to await lifecycle methods when the adapter implements `AsyncStreamablePort[T]`. This avoids forcing adapters to duplicate lifecycle plumbing or wrap async operations in synchronous shims.

**Framework changes:**

1. Define `AsyncStreamablePort[T]` protocol in `cosalette._stream`
2. Update `run_stream` to detect which protocol the adapter implements (sync or async) and call lifecycle methods accordingly
3. Allow app adapters to register either `StreamablePort[T]` or `AsyncStreamablePort[T]`

#### Adapter Access Without Lifecycle Ownership Confusion

Allow handlers to inject the concrete adapter type (e.g., `JeeLinkPort`) while the framework owns lifecycle via the registered `AsyncStreamablePort[T]` or `StreamablePort[T]`. The framework should:

- Call lifecycle methods (`open`, `start_scan`, `register_callback`, `stop_scan`, `close`) as the port owner
- Inject the concrete port instance into the handler for non-stream operations (e.g., `set_led`, `set_config`, `query_status`)

The current `_check_no_port_in_signature` validation forbids parameters annotated as `StreamablePort[T]`, which is correct (the framework owns that lifecycle). However, the framework lacks a clear single-source lifecycle model when the same instance is both the stream source and an app adapter. The framework should:

- Continue to forbid injecting `StreamablePort[T]` directly (reserved for framework lifecycle)
- Allow injecting the concrete adapter type registered in the app's adapter map while clarifying lifecycle ownership
- Document when the framework manages lifecycle vs. when the handler may call adapter methods

**Framework changes:**

1. Clarify lifecycle ownership rules: when a concrete adapter is injectable, which methods are framework-managed vs. handler-accessible
2. Document that handlers receive the adapter instance but must not call lifecycle methods (framework owns lifecycle)
3. Update `_validate_stream_signature` to inject the concrete adapter from the registry when requested by type hint

#### AppHarness Parity for Stream Tests

Extend `AppHarness.inject_stream` to accept `DeviceContext` and `DeviceStore` overrides, matching production stream-handler capabilities. This enables integration tests to:

- Verify raw frame publishing via captured `DeviceContext` calls
- Verify registry restore and persistence via captured `DeviceStore` calls
- Test staleness detection, heartbeat logic, and graceful shutdown

**Framework changes:**

1. Add `ctx: DeviceContext | None = None` parameter to `inject_stream`
2. Add `store: DeviceStore | None = None` parameter to `inject_stream`
3. Include `ctx` and `store` in the provider map if supplied, otherwise use harness defaults

---

## Alternative Options

### Option B: App-Side Adapter Shim Registered as StreamablePort[SensorReading]

**Approach:** Create a thin shim in jeelink2mqtt that wraps `JeeLinkPort` and implements the synchronous `StreamablePort[SensorReading]` protocol. Register the shim with the framework, keep the async `JeeLinkPort` for handler injection.

**Pros:**

- No framework changes required
- Decouples adapter's async lifecycle from framework's sync lifecycle expectations

**Cons:**

- Duplicates lifecycle plumbing in every app with async adapters
- Shim must bridge async lifecycle methods to sync interface, introducing `asyncio.run(...)` or background task complexity
- Still cannot inject `DeviceContext` or `DeviceStore` without framework changes
- Does not solve the integration test gap (`AppHarness.inject_stream` still lacks DI parity)

**Verdict:** Defers the problem to app code; does not provide a reusable solution.

---

### Option C: Keep Receiver as `@app.device` Until cosalette 0.4.x

**Approach:** Defer cap-5xy until the framework implements Option A. Keep the current `@app.device` receiver implementation, which satisfies all integration tests and acceptance criteria except the "uses framework stream feature" requirement.

**Pros:**

- No immediate rework required
- Allows time for framework enhancements to land and stabilize
- Current implementation is fully tested and proven

**Cons:**

- Delays adoption of the `@app.stream` pattern
- Does not demonstrate the intended stream-based architecture
- May create precedent for other apps to stay on `@app.device` indefinitely

**Verdict:** Pragmatic short-term solution; does not block other work.

---

### Option D: Split Stream Processing Into Return-Value-Only Telemetry

**Approach:** Redesign the receiver so that stream processing is stateless and returns telemetry values instead of publishing directly. A separate orchestrator (`@app.device` or `@app.loop`) would call the stream processor and handle publishing.

**Example:**

```python
@app.stream(summary="LaCrosse frame parser")
async def parse_frames(
    stream: cosalette.Stream[SensorReading],
) -> AsyncIterator[Telemetry]:
    async for reading in stream:
        yield _to_telemetry(reading)

@app.device(summary="Receiver orchestrator")
async def receiver(ctx: DeviceContext, parser: AsyncIterator[Telemetry], ...) -> None:
    async for telemetry in parser:
        await ctx.publish(...)
```

**Pros:**

- Stream handler becomes pure logic with no side effects
- Aligns with functional programming principles

**Cons:**

- Does not fit the stateful receiver shape where registry updates, calibration, mapping, and staleness detection are interleaved with frame processing
- Requires two decorators and a hand-off mechanism between them
- Increases complexity for the common case where stream processing and publishing are tightly coupled
- Still requires `DeviceContext` and `DeviceStore` injection somewhere, so does not avoid framework changes

**Verdict:** Mismatched pattern for stateful receivers; increases boilerplate.

---

## Acceptance Criteria (Framework Enhancement)

When the framework implements Option A, the following must be true:

1. **DeviceContext injection:** `@app.stream` handlers can declare `ctx: cosalette.DeviceContext` and receive a valid instance.
2. **DeviceStore injection:** `@app.stream` handlers can declare `store: cosalette.DeviceStore` and receive a valid instance.
3. **Async lifecycle support:** `AsyncStreamablePort[T]` protocol is defined, and `run_stream` awaits lifecycle methods when the adapter implements it.
4. **Concrete adapter injection:** `@app.stream` handlers can declare the concrete adapter type (e.g., `jeelink: JeeLinkPort`) while the framework owns lifecycle via `AsyncStreamablePort[SensorReading]` registration.
5. **AppHarness parity:** `AppHarness.inject_stream` accepts `ctx` and `store` overrides, enabling integration tests to verify publishing and persistence.
6. **Documentation:** Framework docs explain the difference between `@app.device` and `@app.stream`, when to use each, and how to implement async stream sources.
7. **Backward compatibility:** Existing `@app.device` receivers continue to work without modification.

---

## Migration Path (jeelink2mqtt After Framework Support Lands)

Once the framework implements Option A:

1. **Update adapter registration:**
    - Keep `JeeLinkPort` registered in the app adapter map
    - Add an explicit stream-source registration for `AsyncStreamablePort[SensorReading]`, or allow the framework to derive it from the `JeeLinkPort` registration
    - Ensure `JeeLinkPort` implements `AsyncStreamablePort[SensorReading]`
2. **Convert receiver to `@app.stream`:**
   - Change decorator from `@app.device` to `@app.stream`
   - Add `stream: cosalette.Stream[SensorReading]` parameter
   - Inject `ctx: DeviceContext`, `store: DeviceStore`, `jeelink: JeeLinkPort`, `settings: Jeelink2MqttSettings`, `state: SharedState`
   - Replace `async for reading in jeelink:` with `async for reading in stream:`
   - Remove async context manager usage (`async with jeelink:`)
   - Gate `availability/online` publishes on offline→online state transition (not unconditionally per reading); use `asyncio.gather` for concurrent offline publishes in the `finally` block
3. **Update integration tests:**
    - Use `harness.inject_stream` for stream-specific behavior
    - Pass or configure `ctx`, `store`, `jeelink`, `settings`, and `state` providers
   - Verify raw publishing, calibrated state, mapping, staleness, heartbeat, and shutdown
4. **Simplify main.py:**
   - Remove explicit port lifecycle calls
   - Trust framework to manage `open`, `start_scan`, `register_callback`, `stop_scan`, `close`
   - Match the shape described in [jeelink2mqtt-main-simplification.md](jeelink2mqtt-main-simplification.md)
5. **Close cap-5xy and cap-v6y** once all acceptance criteria are met and integration tests pass.

---

## Risks and Open Questions

### Risks

- **Framework API surface expansion:** Adding `AsyncStreamablePort[T]`, clarifying lifecycle ownership for adapter injection, and extending DI for streams increases the framework's API surface. This must be balanced against the benefit of supporting stateful receivers.
- **Lifecycle contract ambiguity:** If handlers can inject the concrete adapter, the framework must clearly document that lifecycle methods are off-limits to handlers. Runtime guards or static type checks may help enforce this.
- **Migration churn:** Other apps using `@app.stream` may need to update if the lifecycle protocol changes from sync to async.

### Open Questions

1. **Sync vs. async lifecycle:** Should the framework deprecate `StreamablePort[T]` in favor of `AsyncStreamablePort[T]`, or support both indefinitely?
2. **Port injection semantics:** Should the framework use a dedicated `@app.stream_port` decorator to register stream sources, making lifecycle ownership explicit?
3. **State restoration timing:** Should `DeviceStore` injection trigger automatic state restoration before the handler runs, or leave it to the handler?
4. **Backport strategy:** Can these enhancements land in cosalette 0.3.14, or do they require a minor version bump to 0.4.0?

---

## Recommendation

**Implement Option A** to extend the `@app.stream` runtime for stateful receivers. This enhancement:

- Achieves parity with `@app.device` for dependency injection and persistence
- Supports async adapter lifecycle without forcing apps to implement sync shims
- Enables integration tests to verify full receiver behavior via `AppHarness.inject_stream`
- Provides a reusable pattern for other apps with similar stateful stream processing needs

**Defer cap-5xy** until the framework enhancement lands. Keep the current `@app.device` receiver implementation in jeelink2mqtt, which satisfies all integration test requirements and remains fully functional.

**Do not attempt workarounds** like Option B (app-side shim) or Option D (split orchestrator), as they increase complexity without solving the core DI and lifecycle gaps.

Once the framework supports Option A, migrate jeelink2mqtt to `@app.stream` following the migration path described above. This will close cap-5xy, the final open child of cap-v6y.
