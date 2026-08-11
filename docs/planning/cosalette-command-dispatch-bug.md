# Bug Report: command handlers are serialised on the MQTT read loop

**Status:** **resolved in cosalette 0.6.1** — see
[Resolution](#resolution-cosalette-061) **Raised by:** cosalette-apps, while planning the
wiz2mqtt migration (beads epic `cap-10u`) **Verified against:** cosalette 0.6.0,
installed wheel — `_mqtt/_client.py`,
`_mqtt/_router.py`, `_runners/_command_runner.py`, `_context/_device_context.py`,
`_runners/_stream_types.py`, `_runners/_telemetry_runner.py`, `_wiring/_context.py`,
`_wiring/_tasks.py`, `_wiring/_task_lifecycle.py`, `_health/_reporter.py`
**Index:** [wiz2mqtt framework proposals](wiz2mqtt-framework-proposals.md)

This is filed as a **bug**, not an enhancement. Every cosalette app that performs slow
or unreliable I/O inside an `@app.command` handler is affected; the framework offers no
knob to opt out; and the failure mode is silent — the app keeps reporting itself
healthy while it has stopped accepting commands.

## Symptom

An app registers several command-bearing entities. One entity's handler blocks — the
device it talks to is powered off, off-network, or simply slow. For the duration of
that one call, **no other entity's commands are processed**, regardless of how
unrelated they are. Inbound messages are not dropped; they sit unread in the client
socket and the broker's outbound queue until the blocked handler returns.

If the handler never returns, the app stops responding to commands permanently. It does
not crash, log an error, or go offline:

- the heartbeat task keeps publishing `status: "online"` to `{prefix}/status`
  (`_health/_reporter.py:199`), because it runs on its own task
  (`_wiring/_task_lifecycle.py:68`);
- the LWT never fires, because it is a broker-side reaction to TCP disconnection
  (`_health/_reporter.py:83-88`) and the TCP connection is perfectly healthy;
- `@app.telemetry` and `@app.device` handlers keep publishing state, because they get
  their own tasks (`_wiring/_tasks.py:67-75`, `_wiring/_task_lifecycle.py:115`, `:142`).

To Home Assistant, and to any other consumer, the app is alive and its entities are
reporting. Commands simply have no effect. There is no signal anywhere that says
otherwise.

## Finding 1 — inbound messages are awaited inline on the single read loop

The connection loop awaits each dispatch before reading the next message
(`_mqtt/_client.py:269-270`):

```python
async for message in client.messages:
    await self._dispatch(message)
```

`_dispatch` (defined at `_mqtt/_client.py:290`) decodes the payload and then awaits
every registered callback in turn (`_mqtt/_client.py:337-339`):

```python
for cb in self._callbacks:
    try:
        await cb(topic, payload)
```

The only callback the framework registers is the topic router
(`_wiring/_context.py:307`, `mqtt.on_message(router.route)`). `TopicRouter.route` awaits
the matched per-device handler directly (`_mqtt/_router.py:118`, and `:99` for the root
handler):

```python
await handler(topic, payload)
```

That handler is the proxy closure built by `CommandRunner`
(`_runners/_command_runner.py:349-363`), which awaits `run_command`
(`:357`), which awaits the user's function (`:225`):

```python
result = await reg.func(**kwargs)
```

There is no `asyncio.create_task` anywhere on this path. `create_task` appears 18 times
in the 0.6.0 tree — for the connection loop itself, connect callbacks, heartbeat,
health checks, device tasks, telemetry tasks, stream watchers, and adapter lifecycle —
and **not once** between `client.messages` and a user command handler. The chain from
socket read to user code is a single unbroken `await`.

Consequence: the read loop is a global critical section covering every command handler
in the app. Concurrency between entities, which the framework provides for every other
handler archetype, does not exist for commands.

## Finding 2 — nothing on the command path is time-bounded

`@app.telemetry` accepts `timeout=` and applies it with `asyncio.wait_for`
(`_runners/_telemetry_runner.py:983-986`, inside `_try_invoke` at `:967`):

```python
if isinstance(reg.timeout, (int, float)) and not isinstance(reg.timeout, bool):
    result = await asyncio.wait_for(coro, reg.timeout)
```

`@app.command` has no equivalent. Its decorator signature (`_app/_command.py:73`)
accepts `name`, `init`, `enabled`, `sub`, `sub_key`, `summary`, `state_model`,
`payload_model`, `behavior`, `effects`, `unavailable_on` — no `timeout`, no `retry`, no
`concurrency`. `_CommandRegistration` (`_registration/_model.py`) carries no `timeout`
field, while `_TelemetryRegistration` in the same module does.

`asyncio.wait_for` / `asyncio.timeout` are used in exactly four places in 0.6.0 — the
telemetry runner, the health-check adapter probe (`_health/_checker.py:115`), the schema
monitor (`_schema/_monitor.py:185`), and task-lifecycle shutdown
(`_wiring/_task_lifecycle.py:166`). None of them is on the command path.

So a handler that hangs is not merely slow — it wedges the read loop for the process
lifetime. `run_command` wraps the call in `try/except Exception` and publishes errors
(`_runners/_command_runner.py:262-266`), but an exception is not what happens here.
Nothing is ever raised.

The two findings compound: Finding 1 means one handler's latency is charged to every
entity, and Finding 2 means that latency has no upper bound.

## Finding 3 — the `@app.device` escape hatch decouples, but is unbounded and undeclared

There is a workaround. `@app.device` plus `ctx.commands()` sets `_commands_consumed`,
which makes the device proxy enqueue rather than call
(`_runners/_command_runner.py:398-404`):

```python
elif _ctx._commands_consumed and sub_topic is None:
    cmd = Command(topic=topic, payload=payload, timestamp=_ctx.clock.now())
    await _ctx._command_queue.put(cmd)
```

The device's own task then drains the queue, so the read loop is released immediately.
This works, and it is what a downstream app has to reach for today. It has two costs.

**The queue is unbounded.** `_context/_device_context.py:163`:

```python
self._command_queue: asyncio.Queue[Command] = asyncio.Queue()
```

No `maxsize`, so `put` never blocks and never drops. If the consuming loop is slower
than the inbound command rate — precisely the situation the escape hatch exists to
handle — the queue grows without limit. The failure mode moves from "commands stall" to
"memory grows and commands are executed minutes late, in order, long after they were
meaningful". For a light, executing a five-minute-old `ON` after the user has already
given up and pressed `OFF` is worse than dropping it.

This is the more striking because the framework has already made this exact decision
for streams. `_runners/_stream_types.py:23`:

```python
BackpressurePolicy = Literal["drop_newest", "drop_oldest", "raise"]
```

with the policy applied in `Stream._enqueue_with_policy`
(`_runners/_stream_types.py:172-182`), and exposed on the decorator — `@app.stream`
takes `maxsize` and `backpressure`, defaulting to `drop_newest`. The design work is
done; commands just never inherited it.

**The command channel disappears from the contract.** Verified by building a two-handler
app against 0.6.0 and dumping the AsyncAPI document:

```text
bulb_cmdCommand          address=wiz2mqtt/bulb_cmd/set     (receive)
bulb_devState            address=wiz2mqtt/bulb_dev/state   (send)
```

The `@app.command` registration emits a `receive` channel on `.../set`. The
`@app.device` registration emits **only** a `send` channel on `.../state` — zero
inbound channels — even though the router subscribes on its behalf to
`wiz2mqtt/bulb_dev/set` and `wiz2mqtt/bulb_dev/+/set`
(`TopicRouter.subscriptions`, `_mqtt/_router.py:182-196`).

The cause is in the generator: `_build_channel_entry` sets
`is_command_input = kind == "command"` (`_schema/_asyncapi.py:434`), and devices are
registered with `kind="device"` (`:703-719`), so they take the state branch
unconditionally. A device may declare `payload_model=`, but it produces no receive
channel.

The app therefore subscribes to a topic it does not document. Downstream tooling that
consumes the manifest — discovery generation, ACL derivation, schema enforcement —
cannot see the command surface at all. Choosing the workaround for Finding 1 means
giving up the contract.

## Blast radius

The trigger is not exotic. It is any command handler that talks to a device over the
network, which is most of them.

The concrete case that prompted this report: an app fronting **14 WiZ bulbs**, each a
separate entity with its own command topic, all on one read loop. WiZ bulbs are driven
by unacknowledged UDP pushes; a bulb cut at the wall switch, asleep, or off-network does
not answer, and the push waits out whatever client-side timeout exists — or forever, if
none does.

So a single bulb switched off at the wall is enough to stall commands for the other
thirteen. A "turn off the living room" scene that touches several bulbs serialises into
a chain of timeouts, and the last bulb in the group responds seconds later or not at
all. With no framework-level timeout, one unreachable bulb can end command processing
for the entire app until it is restarted.

Scale sharpens this but does not cause it. Two entities are enough; 14 just makes it a
daily occurrence rather than a rare one.

**This does not block building the app.** The handlers work, the tests pass, the entity
model is sound. It makes the result unshippable in practice: an app whose lights stop
responding when one bulb is off at the wall, and which reports itself healthy while
doing so, cannot be put in front of a household.

## Reproduction

The following drives the real `MqttClient._dispatch` and `TopicRouter.route` with the
loop body copied verbatim from `_mqtt/_client.py:269-270`. It needs no broker.

```python
import asyncio, time
from dataclasses import dataclass

from cosalette._mqtt._client import MqttClient
from cosalette._mqtt._router import TopicRouter
from cosalette._settings import MqttSettings


@dataclass
class FakeMessage:
    topic: str
    payload: bytes


async def main() -> None:
    router = TopicRouter(topic_prefix="wiz2mqtt")
    log, t0 = [], time.monotonic()

    async def slow(topic: str, payload: str) -> None:
        log.append((f"slow start {topic}", time.monotonic() - t0))
        await asyncio.sleep(2.0)  # a bulb that stopped answering
        log.append((f"slow done  {topic}", time.monotonic() - t0))

    async def fast(topic: str, payload: str) -> None:
        log.append((f"fast done  {topic}", time.monotonic() - t0))

    router.register("bulb_kitchen", slow)
    for n in range(1, 4):
        router.register(f"bulb_{n}", fast)

    client = MqttClient(settings=MqttSettings(host="localhost"))
    client.on_message(router.route)

    messages = [
        FakeMessage("wiz2mqtt/bulb_kitchen/set", b'{"state":"ON"}'),
        FakeMessage("wiz2mqtt/bulb_1/set", b'{"state":"ON"}'),
        FakeMessage("wiz2mqtt/bulb_2/set", b'{"state":"ON"}'),
        FakeMessage("wiz2mqtt/bulb_3/set", b'{"state":"ON"}'),
    ]

    # Verbatim loop body from cosalette/_mqtt/_client.py:269-270
    for message in messages:
        await client._dispatch(message)

    for line, at in log:
        print(f"t+{at:5.2f}s  {line}")


asyncio.run(main())
```

Observed output on cosalette 0.6.0:

```text
t+ 0.00s  slow start wiz2mqtt/bulb_kitchen/set
t+ 2.00s  slow done  wiz2mqtt/bulb_kitchen/set
t+ 2.00s  fast done  wiz2mqtt/bulb_1/set
t+ 2.00s  fast done  wiz2mqtt/bulb_2/set
t+ 2.00s  fast done  wiz2mqtt/bulb_3/set
```

Three unrelated entities, each with an instantaneous handler, all complete only after
the slow one. Raise the sleep and the delay tracks it exactly. Replace it with
`asyncio.Event().wait()` and the other three never run.

## Proposed fix

Three parts. The first is the bug; the other two are what stop it recurring in a
different shape.

**1. Dispatch commands on per-entity tasks.** The router already knows the entity a
message belongs to (`_mqtt/_router.py:104-118`). Hand off there — or in the command
proxy — to a per-entity consumer task instead of awaiting inline, so the read loop
returns to `client.messages` immediately. Ordering must stay FIFO *within* an entity;
a light that receives `ON` then `OFF` must not end up on. Across entities there is no
ordering to preserve, which is the whole point.

Precedent and machinery exist: `start_device_tasks` already builds a name→tasks map
(`_wiring/_tasks.py:60-77`) used for per-adapter cancellation on restart, so
per-entity task tracking and shutdown cancellation follow the established pattern.

**2. Bound the queue, with a declarable backpressure policy.** Reuse
`BackpressurePolicy` from `_runners/_stream_types.py:23` rather than inventing a second
vocabulary, and expose `maxsize=` / `backpressure=` on `@app.command` and `@app.device`
the way `@app.stream` already exposes them. This also fixes the unbounded queue at
`_context/_device_context.py:163`.

We have no strong view on the default and it is properly an upstream call.
`drop_oldest` matches the semantics of idempotent state-setting commands — the newest
`ON`/`OFF` supersedes the one before it — but is wrong for commands with cumulative
side effects, so a conservative default with an easy opt-in is defensible. What matters
downstream is that the queue is bounded and the policy is *declarable per handler*;
a silently unbounded queue leaves an app no way to express "the newest command wins".

**3. Add `timeout=` to `@app.command`.** Same semantics as `@app.telemetry`'s, ideally
the same code path. `run_command` already has the `try/except Exception` wrapper and
publishes through `publish_error_safely` (`_runners/_command_runner.py:262-266`), and
`TimeoutError` is an `Exception` subclass (PEP 3151), so a timeout would fall into the
existing error path and reach the app's error topic with no new plumbing — exactly as
the telemetry runner's docstring notes it composes with retry there.

Part 1 alone stops one entity from taking down the others, which is the acute failure.
It does not remove the need for part 3: without a timeout a hung handler still leaks a
task, still leaves that entity dead, and still reports nothing. Part 3 alone is not
sufficient either — a 10-second timeout on 14 entities still means a 10-second app-wide
stall.

**One request on the shape of the fix.** Please make the per-entity dispatch the default
behaviour rather than an opt-in flag. Handlers that block are the normal case for IoT
apps, not the exception, and an opt-in leaves every existing app carrying the bug until
someone reads the release note and works out that it applies to them. If the change
must be opt-in for compatibility, a startup warning when more than one command entity
is registered without it would at least make the exposure visible.

## Summary

| #   | Finding                                                | Impact                                                            | Suggested fix                                                |
| --- | ------------------------------------------------------ | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| 1   | Command handlers awaited inline on the single read loop | One slow handler stalls commands for every entity in the app       | Per-entity dispatch tasks; read loop never awaits user code   |
| 2   | No timeout anywhere on the command path                 | A hung handler ends command processing for the process lifetime    | `timeout=` on `@app.command`, reusing the telemetry mechanism |
| 3a  | `ctx.commands()` queue is unbounded                     | Escape hatch trades a stall for unbounded growth and stale replays | `maxsize=` / `backpressure=`, reusing `BackpressurePolicy`    |
| 3b  | `@app.device` emits no inbound channel                  | The subscribed command topic is absent from the AsyncAPI contract  | Emit a receive channel for devices that consume commands      |

Findings 1 and 2 are the ones that make an app unshippable. 3a and 3b are what make the
only available workaround unattractive, which is why they belong in the same fix rather
than a follow-up.

## What cosalette-apps is doing

wiz2mqtt will be built against the current framework using ordinary `@app.command`
handlers, with the entity model and tests written as though dispatch were already
concurrent. No local workaround will be implemented:

- The `@app.device` + `ctx.commands()` escape hatch would cost the command channels in
  the generated schema (Finding 3b), and this repository gates its apps on
  `task <app>:schema:check`. Trading contract coverage for concurrency is a bad
  exchange for a defect that is expected to be fixed upstream.
- A hand-rolled dispatch task inside each handler would duplicate, per app, the
  lifecycle and cancellation handling the framework already owns for every other
  handler archetype.

Deployment is gated on the upstream fix: the migration epic carries a gate task
(`cap-10u.7`) blocked until a cosalette release ships it. If the fix lands narrower than
part 1 above — an opt-in flag, or a timeout without per-entity dispatch — the gate stays
open and we will reassess whether the app can ship at all in its 14-bulb configuration.

## Resolution (cosalette 0.6.1)

Shipped as
[cosalette#374](https://github.com/ff-fab/cosalette/issues/374), "fix(command):
concurrent per-entity command dispatch". Verified against the installed 0.6.1 wheel;
gate `cap-10u.7` closed.

All three parts landed, as the default rather than an opt-in:

| Part                          | 0.6.1                                                                                                                                                     |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 — per-entity dispatch       | `TopicRouter.route` enqueues and returns; `_ensure_worker` spawns one `cmd-dispatch:<entity>` task per entity, draining FIFO (`_mqtt/_router.py:148-225`) |
| 2 — `timeout=`                | `@app.command(timeout=…)`, carried on `_CommandRegistration.timeout`                                                                                     |
| 3a — bounded queue            | `maxsize=` / `backpressure=` on `@app.command` and `@app.device`, reusing `BackpressurePolicy` as asked; `DeviceContext._command_queue` now takes a maxsize |
| 3b — device receive channel   | `_build_channel_entry` keys on `kind in {"command", "device_command"}` (`_schema/_asyncapi.py:437`), so a command-consuming device emits a receive channel |

Replaying the reproduction above against 0.6.1 (with `await router.wait_idle()` added,
since dispatch is no longer synchronous with `_dispatch`) and one extra entity receiving
two messages to probe intra-entity ordering:

```text
t+ 0.00s  slow start wiz2mqtt/bulb_kitchen/set
t+ 0.00s  fast done  wiz2mqtt/bulb_1/set
t+ 0.00s  fast done  wiz2mqtt/bulb_2/set
t+ 0.00s  fast done  wiz2mqtt/bulb_3/set
t+ 0.00s  seq start  first
t+ 0.50s  seq done   first
t+ 0.50s  seq start  second
t+ 1.00s  seq done   second
t+ 2.00s  slow done  wiz2mqtt/bulb_kitchen/set
```

The three unrelated entities complete immediately instead of waiting out the stalled
handler, and `first`/`second` stay strictly ordered within their entity — the exact
shape requested. Two lifecycle additions not in the proposal are worth noting for the
app's tests: `TopicRouter.wait_idle()` (await until every queue drains) and
`TopicRouter.aclose()` (cancel workers), which is how a test observes a handler that no
longer runs inline.

The default `maxsize=0` is unbounded, so wiz2mqtt must set `maxsize=`/`backpressure=`
explicitly per bulb rather than inheriting a bounded default; `drop_oldest` is the
policy that matches idempotent state-setting commands, per the argument above.
