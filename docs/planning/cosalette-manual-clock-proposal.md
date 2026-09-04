# Enhancement Proposal: a clock double that makes timing assertions mean something

- **Status:** proposed — upstream ask against cosalette; no downstream fix worth building
- **Raised by:** cosalette-apps, out of the `min_interval=` (ADR-066) adoption in
   commit `f7a78b4`
- **Verified against:** cosalette 0.8.0, the installed wheel, source read directly
   (`testing/_clock.py`, `_clock.py`, `_runners/_device_trigger.py`,
   `_runners/_telemetry_runner.py`) plus a live reproduction of the race asymmetry
- **Implementation lands:** in the cosalette framework repository. There is no downstream
   substitute — the behaviour under test belongs to the runners.
- **Tracking bead:** `cap-o9x`
- **Companion proposal:**
   [a real-sleeping clock](cosalette-real-sleep-clock-proposal.md) — the cheap half of
   the same problem. That one removes the duplication; this one makes the tests correct.

## Summary

`FakeClock` cannot express "this delay happened". `RealSleepClock` can, but only by
spending real seconds and betting on scheduler margins. Neither gives a test the thing
it actually wants: **deterministic control over when time moves.**

Without that, every ADR-066 `min_interval=` assertion in this monorepo is either vacuous
(under `FakeClock`) or racy (under a hand-rolled real-sleep clock). The proposal is to
add a clock whose `sleep` blocks until the test says otherwise.

## Context — why the existing double cannot do this

`FakeClock.sleep` (`testing/_clock.py:36`) yields once and advances virtual time by the
full requested amount. The runners do not merely await sleeps; they race them against
real `asyncio.Event` waits:

| Site | Race |
| ---- | ---- |
| `_device_trigger.py:172-176` | `clock.sleep(deadline - now)` vs. the trigger event |
| `_telemetry_runner.py:645` | `clock.sleep(seconds)` vs. trigger and shutdown |
| `_telemetry_runner.py:886` | same, for group members |

A clock sleep that resolves in one loop iteration wins all of them, for any duration.
Reproduced against the shipped wheel:

```text
sleep(3600) -> real=0.000025s  now()=3600.0
race winner: clock.sleep(3600)          # vs. an event armed 50 ms later
```

So under `FakeClock` the two idioms the apps here depend on both collapse:

- *"An interval this large cannot fire inside the test window."* It fires immediately,
   and keeps firing.
- *"The second trigger was held for `min_interval`."* The ADR-066 gate sleeps the
   remaining window and re-reads `now()` (`_device_trigger.py:144-168`,
   `_telemetry_runner.py:813-823`). `FakeClock` satisfies both halves for free, so the
   window is always already open.

### The concrete damage

`apps/airthings2mqtt/.../test_app_wiring.py:190` —
`test_empty_set_payload_triggers_reread` — states its premise in its own docstring:

> Uses a 1-hour poll interval so the second state publish cannot be a scheduled tick — it
> must be the triggered re-read.

It runs on `FakeClock`, so the premise is false: the 3600 s tick fires on the first loop
iteration. The test asserts `read count >= 2` and would pass with the trigger injection
removed entirely. It may still be asserting something true; it is not asserting the thing
it says it asserts.

The suites that *did* notice worked around it by hand-rolling a real-sleep clock — four
copies, tracked by the
[companion proposal](cosalette-real-sleep-clock-proposal.md) — and paid for it:

```python
_THROTTLE_SECONDS = 0.4
"""Small enough to keep the tests fast, large enough to dwarf the loop
overhead the assertions have to see past."""
```

That comment (`test_app_wiring.py:226-230`) is the honest description of a margin chosen
by experiment. Both throttle tests carry `@pytest.mark.slow`. On a loaded CI runner the
margin is a coin flip, and the failure mode is a flake in a test nobody wants to
re-derive.

## Proposed change

Add a clock whose virtual time only moves when something moves it, in two flavours.
They share one implementation: a sorted set of sleeping waiters keyed by wake deadline.

### 1. `ManualClock` — the test drives time

```python
clock = ManualClock()
harness = AppHarness(app=..., clock=clock, ...)
task = asyncio.create_task(harness.run())

await wait_for_publish_count(harness, state_topic, 1)   # startup publish
await harness.inject_command(name, "", topic=set_topic)
await wait_for_publish_count(harness, state_topic, 2)   # first trigger runs

await harness.inject_command(name, "", topic=set_topic)
await clock.settle()
assert publish_count(harness, state_topic) == 2         # throttle held — exact, not "so far"

await clock.advance(MIN_INTERVAL)
await wait_for_publish_count(harness, state_topic, 3)   # window reopened
```

- `sleep(seconds)` registers a waiter at `now() + seconds` and awaits an `Event`. It
   never completes on its own, so it loses every race it should lose.
- `advance(seconds)` moves `now()` forward, releasing waiters in deadline order and
   yielding between releases so woken tasks make progress.
- `settle()` yields until the loop is quiescent without moving time — this is what turns
   "no publish yet" into a real negative assertion.

The `interval=3600` idiom then works for the reason it claims to: the tick's waiter sits
at t+3600 and the test simply never advances that far.

### 2. `AutoJumpClock` — time moves only when nothing else can

Same waiter set, but when the event loop goes idle the clock jumps to the earliest
pending deadline instead of waiting for the test. Sleep-vs-event races resolve on
ordering rather than on wall time, so throttle windows are observable *and* a
3600-second interval still costs no real time.

This is the more ergonomic default for existing suites: most tests that use `FakeClock`
today for speed would keep passing, while the timing-sensitive ones become meaningful.

Prior art: anyio's `autojump_clock` fixture works exactly this way. It is not directly
usable here — this repo's suites run under `pytest-asyncio` with `asyncio_mode = "auto"`,
not anyio's runner — but the semantics are proven, and worth copying rather than
reinventing.

### 3. Do not change `FakeClock`

`FakeClock`'s current behaviour is load-bearing for a large number of passing tests, and
"advance instantly on sleep" is a legitimate mode for a poll loop under test. Add the new
clocks beside it; do not retarget the name.

Its docstring should gain the caveat the
[companion proposal](cosalette-real-sleep-clock-proposal.md) spells out, so the next
consumer does not spend the same afternoon on it.

## Known-hard part

Quiescence. `advance()` and `settle()` must let woken tasks run to a stable point before
returning, and "the loop has nothing left to do" is not directly observable in asyncio.
The workable approaches, in preference order:

1. Drain by yielding until neither the waiter set nor the set of ready callbacks changes
   across an iteration, with a bounded retry count and a loud failure when the bound is
   hit. Bounded and debuggable.
2. Expose the settle depth as a parameter (`await clock.settle(cycles=8)`) so a test with
   an unusual task graph can ask for more. Ugly, but honest.
3. Inspect the running loop's `_ready` queue. Effective, private-API-dependent, and
   brittle across Python versions — not recommended.

This is the part worth prototyping before committing to an API. It is also the reason the
[real-sleep clock](cosalette-real-sleep-clock-proposal.md) is proposed separately: that
one has no unknowns and can ship first.

## Migration

Nothing breaks. `FakeClock` keeps its behaviour and its name. Downstream adoption is
per-test, and the three affected suites here would convert as:

| Test | Today | After |
| ---- | ----- | ----- |
| airthings / caldates throttle spacing | `RealSleepClock` + 0.4 s window + `@slow` | `ManualClock` + exact negative assertion, no real wait |
| wiz2mqtt push-vs-tick | `RealSleepClock` + `NO_TICK_INTERVAL = 30.0` | `ManualClock`, tick waiter never released |
| jeelink2mqtt heartbeat bound | inline `RealSleepClock` + `3600.0` | `ManualClock`, same |
| airthings `test_empty_set_payload_triggers_reread` | `FakeClock`, premise false | `ManualClock`, premise true as written |

## Acceptance

1. `ManualClock` (and/or `AutoJumpClock`) is exported from `cosalette.testing`, with the
   quiescence contract documented on `advance`/`settle`.
2. A framework test proves an ADR-066 `min_interval=` window is observable under it —
   and fails when `min_interval=` is removed from the registration.
3. `cosalette ai help testing` states which clock to reach for and why.
4. `FakeClock` is unchanged in behaviour.
