"""Unit tests for geiger2mqtt.adapters.fake — the dry-run Poisson pulse source.

Test Techniques Used:
- Specification-based: about 20 CPM over a long simulated run.
- Round-trip Testing: the same seed reproduces the same pulse train.
- Error Guessing: pulses never appear after the current clock time.
- State Transition: entering the context restarts the count.
"""

from __future__ import annotations

import pytest

from geiger2mqtt.adapters.fake import BACKGROUND_CPM, FakePulseCounter
from tests.fixtures.config import FakeTime, make_settings

pytestmark = pytest.mark.unit


def _run(seed: int, minutes: int) -> tuple[FakeTime, FakePulseCounter, int]:
    clock = FakeTime()
    counter = FakePulseCounter(make_settings(), clock=clock, seed=seed)
    total = 0
    for _ in range(minutes):
        since = clock()
        clock.advance(60)
        total += len(counter.snapshot(since=since))
    return clock, counter, total


def test_rate_is_about_background_cpm() -> None:
    _, _, total = _run(seed=42, minutes=600)

    assert total / 600 == pytest.approx(BACKGROUND_CPM, rel=0.05)


def test_same_seed_same_pulses() -> None:
    clock_a, a, _ = _run(seed=7, minutes=10)
    clock_b, b, _ = _run(seed=7, minutes=10)

    assert a.snapshot(since=0.0) == b.snapshot(since=0.0)
    assert a.last_pulse() == b.last_pulse()


def test_no_pulse_after_now() -> None:
    clock, counter, _ = _run(seed=1, minutes=5)

    last = counter.last_pulse()

    assert last is not None
    assert last <= clock()
    assert all(t <= clock() for t in counter.snapshot(since=0.0))


def test_custom_rate() -> None:
    clock = FakeTime()
    counter = FakePulseCounter(make_settings(), clock=clock, seed=3, cpm=600.0)
    clock.advance(60)

    assert len(counter.snapshot(since=0.0)) == pytest.approx(600, rel=0.15)


async def test_enter_restarts_count() -> None:
    clock = FakeTime()
    counter = FakePulseCounter(make_settings(), clock=clock, seed=5)
    clock.advance(600)
    assert counter.last_pulse() is not None

    async with counter as entered:
        assert entered is counter
        assert counter.started_at == clock()
        assert counter.snapshot(since=0.0) == []
