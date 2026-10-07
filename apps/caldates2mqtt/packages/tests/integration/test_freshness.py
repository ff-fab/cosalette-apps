"""Integration tests for the calendar freshness policy.

With the default two-hour ``schedule``, cosalette derives ``stale_after`` for a
calendar as ``2 x 7200 + 72 x 3 = 14616 s`` (ADR-080: a cron schedule has no
implicit timeout, and the default backoff's 60 s cap plus 20 % jitter gives a
72 s allowance per retry). The freshness watchdog checks every 60 s.
caldates2mqtt sets no ``exit_after_stale``, so a stale calendar keeps the app
running until a read succeeds again.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the derived bound
- State Transition: failing -> stale -> ok, without an exit
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette.testing import AppHarness, ManualClock

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import CalDavConnectionError
from caldates2mqtt.settings import CalendarConfig

from .conftest import _DEFAULT_CALENDAR, TOPIC_PREFIX, _FastPollSettings, make_harness

_DEFAULT_SCHEDULE = CalendarConfig.model_fields["schedule"].default
"""Every two hours; the production default, not the fast test schedule."""

_DERIVED_STALE_AFTER = 2 * 7200 + 72 * 3
"""The derived bound for the default schedule; see module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = (_DERIVED_STALE_AFTER // _CHECK_INTERVAL + 1) * _CHECK_INTERVAL
"""The first watchdog check past the derived bound."""

_STATUS_TOPIC = f"{TOPIC_PREFIX}/status"


def _garbage_status(harness: AppHarness) -> str:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    return json.loads(payload)["devices"]["garbage"]["status"]


@pytest.mark.integration
@pytest.mark.slow
async def test_dead_server_marks_calendar_stale_without_exit() -> None:
    """A server that stops answering makes the calendar stale; the app runs on.

    Technique: Boundary Value Analysis — one check before 14616 s the calendar
    is only failing; the heartbeat after the first check past it reports
    ``stale``. The run does not end, and a ``/set`` re-read that succeeds
    returns the calendar to ``ok``.
    """
    reader = FakeCalDavReader()
    reader.fail_next_reads(CalDavConnectionError("server gone"), count=10_000)
    settings = _FastPollSettings(
        calendars=[{**_DEFAULT_CALENDAR, "schedule": _DEFAULT_SCHEDULE}],  # type: ignore[arg-type]
    )
    harness = make_harness(
        reader, settings.calendars, settings=settings, clock=ManualClock()
    )
    elapsed = 0

    async def advance_to(target: int) -> None:
        nonlocal elapsed
        while elapsed < target:
            await harness.advance_time(_CHECK_INTERVAL)
            elapsed += _CHECK_INTERVAL

    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(_STATUS_TOPIC, 1)

        await advance_to(_DERIVED_STALE_AFTER - _CHECK_INTERVAL)
        assert _garbage_status(harness) != "stale"

        await advance_to(_STALE_AT + _CHECK_INTERVAL)
        assert _garbage_status(harness) == "stale"
        assert not task.done()

        reader.failure_sequence.clear()
        await harness.inject_command(None, {}, topic=f"{TOPIC_PREFIX}/garbage/set")
        await harness.wait_for_publish_count(f"{TOPIC_PREFIX}/garbage/state", 1)
        await advance_to(elapsed + _CHECK_INTERVAL)
        assert _garbage_status(harness) == "ok"
        assert not task.done()
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
