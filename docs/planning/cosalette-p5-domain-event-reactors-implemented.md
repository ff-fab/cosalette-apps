# P5 State Reactors: Downstream Upgrade Notes

cosalette 0.4.0 implements the core request from the P5 Framework Enhancement Proposal:
domain-event reactors for `@app.state`.

The goal is to keep shared state objects pure. State classes no longer need methods like
`flush_events(ctx, store)` or private MQTT publishing helpers. Instead, state objects expose
domain-event drains, and top-level reactor functions perform I/O with normal cosalette
dependency injection.

## What Was Implemented

cosalette now provides `@app.react(...)`:

```python
@app.state
def shared_state() -> SharedState:
    return SharedState(...)


@app.react(SharedState, drain=lambda state: state.registry.drain_events())
async def on_registry_events(
    events: list[MappingEvent],
    ctx: cosalette.DeviceContext,
    store: DeviceStore,
    state: SharedState,
) -> None:
    for event in events:
        await publish_mapping_event(ctx, event)

    await publish_mapping_state(ctx, state)
    store["registry"] = state.registry.to_dict()
```

Reactors are flushed automatically by the framework after reaction boundaries:

- `@app.device` async-generator yields
- `@app.stream` async-iterable yields
- successful `@app.telemetry` handlers
- successful `@app.command` handlers

## Differences From The FEP

The implementation differs from the original FEP in a few maintainer-oriented ways.

The FEP proposed `drain="registry.drain_events"` as a string path. cosalette 0.4.0 uses
`drain=lambda state: state.registry.drain_events()` instead. This avoids string-based
runtime lookup and keeps the API idiomatic Python.

The FEP expected drained events to be inferred from the drain return type. The
implementation reserves the parameter name `events` instead. If a reactor declares
`events`, cosalette injects the drained list by name. All other parameters use normal
type-based dependency injection.

The FEP focused mostly on `@app.device` loops. The implementation is broader: reactors
run after `@app.device`, `@app.stream`, `@app.telemetry`, and `@app.command` execution
boundaries.

The FEP treated `@app.device` as the current loop plus automatic flushing. cosalette 0.4.0
makes the boundary explicit with a breaking lifecycle change: long-running `@app.device`
and `@app.stream` handlers must now be async generators or async iterables and `yield`
after each processed unit of work.

## Upgrade Steps For Downstream Apps

Once cosalette 0.4.0 is released, update the dependency:

```bash
uv add "cosalette>=0.4,<0.5"
```

Then migrate long-running device and stream handlers from coroutine loops to
async-generator reaction boundaries.

Before:

```python
@app.device("receiver")
async def receiver(ctx: cosalette.DeviceContext, state: SharedState) -> None:
    while not ctx.shutdown_requested:
        reading = await read_reading()
        state.registry.apply(reading)

        if await state.flush_events(ctx, store):
            last_persist_time = datetime.now(UTC)

        await ctx.sleep(1.0)
```

After:

```python
from collections.abc import AsyncIterator


@app.device("receiver")
async def receiver(
    ctx: cosalette.DeviceContext,
    state: SharedState,
) -> AsyncIterator[None]:
    while not ctx.shutdown_requested:
        reading = await read_reading()
        state.registry.apply(reading)

        yield  # reaction boundary: @app.react handlers run here

        await ctx.sleep(1.0)
```

Then move I/O out of `SharedState`:

- Delete `SharedState.flush_events(ctx, store)`.
- Move MQTT publishing helpers to module-level functions.
- Keep `SharedState` focused on domain data and domain mutations.
- Add one or more `@app.react(SharedState, drain=...)` functions in the composition root.

## Testing Guidance

State objects should now be unit-tested without MQTT or store mocks. Reactor functions can
be tested directly by passing drained events plus fake `ctx` and `store` objects.

Harness and integration tests that execute `@app.device` or `@app.stream` handlers must also
use async-generator handlers with explicit `yield` boundaries. Old coroutine-style handlers
will be rejected by cosalette 0.4.0.
