"""Integration tests for the receiver freshness bound and stale exit policy.

The root ``receiver`` stream declares ``stale_after=receiver_stale_after``:
the longest configured staleness timeout. These tests use a 630 s global
timeout, which keeps the bound off the 60 s check grid. The freshness watchdog
checks every 60 s, so a JeeLink that stops sending at t=0 turns ``"stale"`` at
the 660 s check, and ``exit_after_stale`` stops the app with code 5 at the
first check ``EXIT_AFTER_STALE`` seconds after that.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the bound and the
  exit_after_stale backstop
- State Transition: ok -> stale -> ok on the next frame; ok -> stale -> exit
"""

from __future__ import annotations

import asyncio
import json
import warnings
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import cosalette
import pytest
from cosalette import MockMqttClient, StreamablePort
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, ManualClock

from jeelink2mqtt import main as _main
from jeelink2mqtt.adapters import FakeJeeLinkAdapter
from jeelink2mqtt.models import SensorReading
from jeelink2mqtt.settings import Jeelink2MqttSettings

_STALENESS_TIMEOUT = 630
"""Global sensor timeout, and so the receiver bound (no sensors configured)."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = (_STALENESS_TIMEOUT // _CHECK_INTERVAL + 1) * _CHECK_INTERVAL
"""The first watchdog check past the bound."""

_EXIT_AT = _STALE_AT + int(_main.EXIT_AFTER_STALE)
"""The watchdog check at which the receiver has been stale for the backstop."""

_STATUS_TOPIC = "jeelink2mqtt/status"


class _CountingFakeJeeLinkAdapter(FakeJeeLinkAdapter):
    """Fake adapter exposing lifecycle re-entry to freshness tests."""

    def __init__(self) -> None:
        super().__init__()
        self.entries = 0

    async def __aenter__(self) -> _CountingFakeJeeLinkAdapter:
        self.entries += 1
        return await super().__aenter__()


def _receiver_status(harness: AppHarness) -> str:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    return json.loads(payload)["devices"]["receiver"]["status"]


def _frame() -> SensorReading:
    return SensorReading(
        sensor_id=42,
        temperature=21.5,
        humidity=55,
        low_battery=False,
        timestamp=datetime.now(UTC),
    )


@asynccontextmanager
async def _running(
    *, restart_on_stale: bool = False
) -> AsyncIterator[
    tuple[
        AppHarness,
        _CountingFakeJeeLinkAdapter,
        Callable[[int], object],
        asyncio.Task[None],
    ]
]:
    """Run the shared receiver wiring; yield the harness, clock driver and task."""
    adapter = _CountingFakeJeeLinkAdapter()
    clock = ManualClock()
    app = cosalette.App(
        name="jeelink2mqtt",
        version="0.1.0",
        settings_class=Jeelink2MqttSettings,
        store=MemoryStore(),
        adapters={StreamablePort[SensorReading]: lambda: adapter},
        exit_after_stale=_main.EXIT_AFTER_STALE,
        restart_on_stale=restart_on_stale,
    )
    app.state(_main.shared_state)
    _main.configure_receiver(app)
    harness = AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=clock,
        settings=Jeelink2MqttSettings(
            sensors=[],
            serial_port="/dev/null",
            staleness_timeout_seconds=_STALENESS_TIMEOUT,
            _env_file=None,  # type: ignore[call-arg]
        ),
        shutdown_event=asyncio.Event(),
        run_streams=True,
    )
    elapsed = 0

    async def advance_to(target: int) -> None:
        # One heartbeat at a time, so every check and heartbeat runs in order.
        nonlocal elapsed
        while elapsed < target:
            await harness.advance_time(_CHECK_INTERVAL)
            elapsed += _CHECK_INTERVAL

    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(_STATUS_TOPIC, 1)
        # The framework registers the stream callback once the stream starts.
        await clock.settle(until=lambda: adapter._callback is not None)
        yield harness, adapter, advance_to, task
    finally:
        harness.shutdown_event.set()
        if not task.done():
            done, _ = await asyncio.wait({task}, timeout=2.0)
            if not done:
                task.cancel()
                await asyncio.wait({task}, timeout=1.0)
        if task.done():
            await asyncio.gather(task, return_exceptions=True)
        # Framework health checks may leave an idle default-executor worker.
        # Bound its join so pytest's loop teardown cannot wait indefinitely.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            await asyncio.get_running_loop().shutdown_default_executor(timeout=1.0)


async def _wait_for_adapter_restart(
    harness: AppHarness, adapter: _CountingFakeJeeLinkAdapter
) -> None:
    """Advance through the default cooldown until the stream restarts."""
    for _ in range(300):
        if adapter.entries == 2 and adapter._callback is not None:
            return
        await harness.advance_time(0.1)
    msg = "stale receiver did not re-enter its adapter and register the stream"
    raise AssertionError(msg)


@pytest.mark.integration
async def test_stale_receiver_restarts_adapter_and_recovers_on_next_frame() -> None:
    """A stale root stream re-enters its adapter, then resumes on a frame."""
    async with _running(restart_on_stale=True) as (
        harness,
        adapter,
        advance_to,
        task,
    ):
        adapter.inject(_frame())
        await harness.wait_for_publish_count("jeelink2mqtt/raw/state", 1)
        await advance_to(_STALE_AT)
        await _wait_for_adapter_restart(harness, adapter)

        assert adapter._callback is not None
        assert not task.done()
        adapter.inject(_frame())
        await harness.wait_for_publish_count("jeelink2mqtt/raw/state", 2)
        await advance_to(_STALE_AT + _CHECK_INTERVAL)
        assert _receiver_status(harness) == "ok"


@pytest.mark.integration
async def test_silent_receiver_goes_stale_and_the_next_frame_recovers_it() -> None:
    """No frame for the bound marks the receiver stale; a frame clears it.

    Technique: Boundary Value Analysis — at the check before 630 s the
    receiver is ``ok``; the heartbeat after the 660 s check reports ``stale``
    (the heartbeat at the same tick as the check still has the old status).
    """
    async with _running() as (harness, adapter, advance_to, _task):
        adapter.inject(_frame())
        await harness.wait_for_publish_count("jeelink2mqtt/raw/state", 1)
        await advance_to(_STALE_AT - _CHECK_INTERVAL)
        assert _receiver_status(harness) == "ok"

        await advance_to(_STALE_AT + _CHECK_INTERVAL)
        assert _receiver_status(harness) == "stale"

        adapter.inject(_frame())
        await harness.wait_for_publish_count("jeelink2mqtt/raw/state", 2)
        await advance_to(_STALE_AT + 2 * _CHECK_INTERVAL)
        assert _receiver_status(harness) == "ok"


@pytest.mark.integration
async def test_silent_receiver_exits_for_restart_after_backstop() -> None:
    """A receiver that stays stale for EXIT_AFTER_STALE ends the run with code 5.

    Technique: Boundary Value Analysis — one check before ``_EXIT_AT`` the app
    still runs; one check later the run ends with ``StaleTelemetryError``.
    """
    async with _running(restart_on_stale=True) as (
        _harness,
        adapter,
        advance_to,
        task,
    ):
        await advance_to(_STALE_AT)
        await _wait_for_adapter_restart(_harness, adapter)
        await advance_to(_EXIT_AT - _CHECK_INTERVAL)
        assert not task.done()

        await advance_to(_EXIT_AT + _CHECK_INTERVAL)
        await asyncio.wait_for(_harness.shutdown_event.wait(), timeout=1.0)


@pytest.mark.integration
async def test_receiver_that_never_gets_its_first_frame_exits_after_backstop() -> None:
    """A dry-run receiver with no frames reaches stale and then exits for restart."""
    async with _running(restart_on_stale=True) as (
        _harness,
        adapter,
        advance_to,
        task,
    ):
        await advance_to(_STALE_AT)
        await _wait_for_adapter_restart(_harness, adapter)
        await advance_to(_EXIT_AT - _CHECK_INTERVAL)
        assert not task.done()

        await advance_to(_EXIT_AT + _CHECK_INTERVAL)
        await asyncio.wait_for(_harness.shutdown_event.wait(), timeout=1.0)
