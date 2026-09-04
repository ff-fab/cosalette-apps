# Enhancement Proposal: give a real-sleeping test clock a home in `cosalette.testing`

- **Status:** proposed — upstream ask against cosalette; a downstream fallback exists
   and is described under [If this is declined](#if-this-is-declined)
- **Raised by:** cosalette-apps, out of the `min_interval=` (ADR-066) adoption in
   commit `f7a78b4`
- **Verified against:** cosalette 0.8.0, the installed wheel, source read directly
   (`testing/_clock.py`, `_clock.py`, `_runners/_device_trigger.py`,
   `_runners/_telemetry_runner.py`) plus a live reproduction of the race asymmetry
- **Implementation lands:** in the cosalette framework repository. The downstream
   de-duplication can proceed either way — see the fallback.
- **Tracking bead:** `cap-o9x`
- **Companion proposal:** [a manually-advanced clock](cosalette-manual-clock-proposal.md),
   which supersedes this one for most of the cases below. This proposal is the cheap,
   shippable half; that one is the correct fix.

## Summary

`cosalette.testing` ships exactly one `ClockPort` double, `FakeClock`, whose `sleep`
advances virtual time in zero real time. Any test that needs a *delay to cost something*
has no double to reach for, so consumers hand-roll one. There are now **four** copies of
the same eight-line `RealSleepClock` subclass in this monorepo, every one of them
reaching into `FakeClock`'s private `_time` attribute.

The ask is small: ship the real-sleeping variant next to `FakeClock`, and document what
each one is for.

## Context

`ClockPort` (`_clock.py:15`) has two members, `now()` and `sleep(seconds)`. Production
uses `SystemClock`, where both are real. Tests are offered `FakeClock`
(`testing/_clock.py:14`), where `sleep` is:

```python
async def sleep(self, seconds: float) -> None:
    await asyncio.sleep(0)
    if seconds > 0:
        self._time += seconds
```

That is the right default for the majority of tests — it makes a poll loop run at full
speed. But the runners do not only *sleep*; they **race** a clock sleep against real
`asyncio.Event` waits:

- `_device_trigger.py:172-176` — `_wake_before` races `clock.sleep(deadline - now)`
   against the trigger event.
- `_telemetry_runner.py:645` — `_race_sleep_and_trigger` races `clock.sleep(seconds)`
   against the trigger event and shutdown.
- `_telemetry_runner.py:886` — `_sleep_until_wake`, same shape for group members.

Under `FakeClock` the clock sleep completes after a single event-loop yield, so it wins
every one of those races unconditionally, no matter how large the interval. Reproduced
against the shipped 0.8.0 wheel:

```text
sleep(3600) -> real=0.000025s  now()=3600.0
race winner: clock.sleep(3600)          # vs. an event armed 50 ms later
throttle window 0.4s -> virtual elapsed=0.4  real=~0s
```

Two consequences follow, and both are load-bearing for the apps here:

1. **An interval cannot be made unreachable.** The idiom "set `interval=3600` so a
   scheduled tick cannot fire inside this test, therefore the publish I observe must
   have come from a trigger" is false under `FakeClock` — the 3600 s tick fires
   immediately and repeatedly.
2. **A throttle window cannot be observed.** The ADR-066 gate is "sleep the remaining
   window, then re-read `now()`" (`_device_trigger.py:144-168`,
   `_telemetry_runner.py:813-823`). `FakeClock` satisfies both halves for free, so the
   window is always already reopened and `min_interval=` is unobservable.

## The duplication

Four copies, textually near-identical, all subclassing `FakeClock` and assigning to its
private `_time`:

| Location | Purpose |
| -------- | ------- |
| `apps/airthings2mqtt/packages/tests/integration/conftest.py:57` | throttle spacing |
| `apps/caldates2mqtt/packages/tests/integration/conftest.py:71` | throttle spacing |
| `apps/wiz2mqtt/packages/tests/integration/conftest.py:42` | unreachable tick (`NO_TICK_INTERVAL = 30.0`) |
| `apps/jeelink2mqtt/packages/tests/integration/test_event_driven_acceptance.py:90` | unreachable heartbeat (`NO_HEARTBEAT_SECONDS = 3600.0`) |

The fourth is not even in a `conftest.py` — it is declared inline in a test module, with
a comment pointing at the bead that tracks this. The bead itself recorded three; the
count is four.

Each copy does the same thing:

```python
class RealSleepClock(FakeClock):
    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        if seconds > 0:
            self._time += seconds
```

Note the `self._time` write. `FakeClock` documents `_time` as settable
(`testing/_clock.py:17-27`), but it is still a private name on a `@dataclass`, and four
downstream subclasses depending on it makes it de facto public API. Shipping the
subclass upstream turns that from an accident into a decision.

## Proposed change

### 1. Add `RealSleepClock` to `cosalette.testing`

```python
@dataclass
class RealSleepClock(FakeClock):
    """A :class:`FakeClock` whose ``sleep`` waits for real wall-clock time.

    Use this when a test's meaning depends on a delay actually costing
    something: proving a scheduled tick is unreachable inside the test
    window, or measuring the spacing ``min_interval=`` imposes.  Pay for
    it with intervals measured in fractions of a second.
    """

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        if seconds > 0:
            self._time += seconds
```

Export it from `cosalette/testing/__init__.py` alongside `FakeClock`, and list it in the
module docstring's provided-symbols block.

### 2. Document the choice at the point of use

`FakeClock`'s docstring should say what it is not suitable for. Suggested addition:

> `sleep` advances virtual time with no real delay, so it wins any race against a real
> `asyncio` event. Tests that assert a *duration* — that a tick was unreachable, or that
> a `min_interval=` window held — measure nothing under this clock; use
> `RealSleepClock` for those.

The same distinction belongs in `cosalette ai help testing`, which currently presents
`FakeClock` as the clock double with no caveat.

### 3. Settle `_time`

Two options, either acceptable:

- Keep `_time` and treat subclassing as supported, which the new export makes explicit.
- Add a public `advance(seconds)` and have both clocks use it, leaving `_time` genuinely
   private. This is a prerequisite for the
   [companion proposal](cosalette-manual-clock-proposal.md) anyway.

The second is preferred if both proposals are taken.

## What this does not fix

Real sleeping buys correctness at the cost of wall-clock time and CI determinism. The
two throttle tests here already carry `@pytest.mark.slow` and use a 0.4 s window chosen
to "dwarf the loop overhead the assertions have to see past"
(`test_app_wiring.py:226-230`) — which is an admission that the margin is empirical, not
guaranteed. On a loaded runner, a real-sleep timing assertion is a flake waiting to
happen.

That is the argument for the [manually-advanced clock](cosalette-manual-clock-proposal.md),
which makes the same assertions deterministic *and* instant. This proposal remains worth
taking regardless: it costs one class and one export, it can ship in a patch release, and
it removes four duplicates today.

## If this is declined

The downstream fallback is route (b) of `cap-o9x`: hoist one `RealSleepClock` into a
shared in-repo test-fixture module that all four suites import. That satisfies the
bead's first acceptance criterion, but leaves every other cosalette consumer to
rediscover the same gap, and keeps the private-`_time` dependency in downstream code
where upstream cannot see it.

## Acceptance

1. `from cosalette.testing import RealSleepClock` works.
2. `FakeClock`'s docstring names the cases it cannot serve.
3. The four downstream copies are deleted in favour of the import.
