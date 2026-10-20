"""Unit tests for geiger2mqtt.devices.radiation — the telemetry handler.

The counter is a FakePulseCounter at 0 CPM, so the only pulses are the ones a
test records at the fake clock's current time.

Test Techniques Used:
- Boundary Value Analysis: no reading before 60 s, the first one at 60 s;
  no-pulse timeout one second before and at the limit.
- Specification-based: cpm and dose rates for a known pulse train; the
  average scales by elapsed time until the window has filled.
- Equivalence Partitioning: no-pulse timeout enabled vs disabled (0).
- Error Guessing: a pulse older than the average window does not count.
"""

from __future__ import annotations

import pytest

from geiger2mqtt.adapters.fake import FakePulseCounter
from geiger2mqtt.devices.radiation import NoPulseError, RadiationState, radiation
from geiger2mqtt.settings import Geiger2MqttSettings
from tests.fixtures.config import FakeTime, make_settings

pytestmark = pytest.mark.unit

FACTOR = 0.0057


def _counter(settings: Geiger2MqttSettings, clock: FakeTime) -> FakePulseCounter:
    return FakePulseCounter(settings, clock=clock, cpm=0.0)


def _pulses(counter: FakePulseCounter, clock: FakeTime, n: int, gap: float) -> None:
    for _ in range(n):
        clock.advance(gap)
        counter.record()


@pytest.mark.parametrize(("elapsed", "published"), [(59.999, False), (60.0, True)])
async def test_no_reading_until_cpm_window_is_full(
    settings: Geiger2MqttSettings, fake_time: FakeTime, elapsed: float, published: bool
) -> None:
    counter = _counter(settings, fake_time)
    fake_time.advance(elapsed)

    result = await radiation(counter, settings)

    assert (result is not None) is published


async def test_reading_from_pulses(
    settings: Geiger2MqttSettings, fake_time: FakeTime
) -> None:
    """30 pulses in the first minute: 30 CPM, average equal to the rate."""
    counter = _counter(settings, fake_time)
    _pulses(counter, fake_time, 30, gap=2.0)

    result = await radiation(counter, settings)

    assert result == RadiationState(
        cpm=30, dose_rate=round(30 * FACTOR, 4), dose_rate_avg=round(30 * FACTOR, 4)
    )


async def test_average_scales_until_window_fills(fake_time: FakeTime) -> None:
    """At 5 min, 100 pulses mean 20 CPM on average, not 100 / 15."""
    settings = make_settings(average_window=900)
    counter = _counter(settings, fake_time)
    _pulses(counter, fake_time, 100, gap=3.0)

    result = await radiation(counter, settings)

    assert result is not None
    assert result.cpm == 20
    assert result.dose_rate_avg == round(20 * FACTOR, 4)


async def test_old_pulses_leave_the_average(fake_time: FakeTime) -> None:
    """Technique: Error Guessing — the average covers only the last window."""
    settings = make_settings(average_window=120, no_pulse_timeout=0)
    counter = _counter(settings, fake_time)
    _pulses(counter, fake_time, 60, gap=1.0)  # 60 pulses in the first minute
    fake_time.advance(150)  # all of them now older than 120 s

    result = await radiation(counter, settings)

    assert result == RadiationState(cpm=0, dose_rate=0.0, dose_rate_avg=0.0)


@pytest.mark.parametrize(("silence", "raises"), [(299.0, False), (300.0, True)])
async def test_no_pulse_timeout(
    fake_time: FakeTime, silence: float, raises: bool
) -> None:
    settings = make_settings(no_pulse_timeout=300)
    counter = _counter(settings, fake_time)
    _pulses(counter, fake_time, 1, gap=10.0)
    fake_time.advance(silence)

    if raises:
        with pytest.raises(NoPulseError, match="No pulse for 300 s"):
            await radiation(counter, settings)
    else:
        assert await radiation(counter, settings) is not None


async def test_no_pulse_since_start(fake_time: FakeTime) -> None:
    """Without any pulse, the timeout counts from the start."""
    settings = make_settings(no_pulse_timeout=300)
    counter = _counter(settings, fake_time)
    fake_time.advance(300)

    with pytest.raises(NoPulseError):
        await radiation(counter, settings)


async def test_zero_timeout_disables_the_check(fake_time: FakeTime) -> None:
    settings = make_settings(no_pulse_timeout=0)
    counter = _counter(settings, fake_time)
    fake_time.advance(86_400)

    assert await radiation(counter, settings) == RadiationState(
        cpm=0, dose_rate=0.0, dose_rate_avg=0.0
    )
