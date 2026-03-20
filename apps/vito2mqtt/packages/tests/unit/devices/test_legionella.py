# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for devices/legionella.py — Heating window check & device state machine.

Test Techniques Used:
- Specification-based: Verify is_within_heating_window contract
- Boundary Value Analysis: Exact margin boundary, one-minute-before boundary
- Equivalence Partitioning: Inside/outside window, empty/None schedules
- Cross-reference: TIMER_SIGNAL_FOR_DAY values exist in COMMANDS registry
- State Transition Testing: Legionella device lifecycle
  (idle → checking → heating → restoring)
- Error Guessing: Startup recovery from interrupted treatment
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import datetime, time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from vito2mqtt.devices.legionella import (
    _STORE_KEY_ACTIVE,
    _STORE_KEY_ORIGINAL_SETPOINT,
    LEGIONELLA_SETPOINT_SIGNAL,
    TIMER_SIGNAL_FOR_DAY,
    _legionella_device,
    is_within_heating_window,
    register_legionella,
)
from vito2mqtt.optolink.codec import CycleTimeSchedule
from vito2mqtt.optolink.commands import COMMANDS
from vito2mqtt.ports import OptolinkPort

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Standard single-window schedule: 06:00–14:00
_WINDOW_06_14: CycleTimeSchedule = [
    [[6, 0], [14, 0]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
]


def _schedule_with_two_windows() -> CycleTimeSchedule:
    """Two active windows: 06:00–10:00 and 16:00–22:00."""
    return [
        [[6, 0], [10, 0]],
        [[16, 0], [22, 0]],
        [[None, None], [None, None]],
        [[None, None], [None, None]],
    ]


# ===========================================================================
# is_within_heating_window
# ===========================================================================


class TestIsWithinHeatingWindow:
    """Tests for the is_within_heating_window pure function.

    Technique: Specification-based — verify the matching logic against the
    documented contract (start <= now < effective_end).
    """

    def test_within_active_window(self) -> None:
        """now=10:00, window 06:00–14:00, margin=30 → True.

        Technique: Equivalence Partitioning — clearly inside the window.
        """
        # Arrange
        now = time(10, 0)

        # Act
        result = is_within_heating_window(_WINDOW_06_14, now, safety_margin_minutes=30)

        # Assert
        assert result is True

    def test_outside_all_windows(self) -> None:
        """now=03:00, window 06:00–14:00, margin=30 → False.

        Technique: Equivalence Partitioning — before the window starts.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(3, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_near_end_within_margin(self) -> None:
        """now=13:35, window 06:00–14:00, margin=30 → False (only 25 min left).

        Technique: Boundary Value Analysis — inside the window but too close
        to the end for the safety margin.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 35), safety_margin_minutes=30
        )

        assert result is False

    def test_exactly_at_margin_boundary(self) -> None:
        """now=13:30, window 06:00–14:00, margin=30 → False.

        Technique: Boundary Value Analysis — effective_end is 13:30,
        condition is now < effective_end so exactly-at is excluded.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 30), safety_margin_minutes=30
        )

        assert result is False

    def test_one_minute_before_margin(self) -> None:
        """now=13:29, window 06:00–14:00, margin=30 → True (31 min left).

        Technique: Boundary Value Analysis — one minute inside the valid zone.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 29), safety_margin_minutes=30
        )

        assert result is True

    def test_before_window_start(self) -> None:
        """now=05:59, window 06:00–14:00, margin=30 → False.

        Technique: Boundary Value Analysis — one minute before the start.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(5, 59), safety_margin_minutes=30
        )

        assert result is False

    def test_exactly_at_window_start(self) -> None:
        """now=06:00, window 06:00–14:00, margin=30 → True.

        Technique: Boundary Value Analysis — start is inclusive.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(6, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_empty_schedule(self) -> None:
        """Empty schedule → False.

        Technique: Equivalence Partitioning — degenerate input.
        """
        result = is_within_heating_window([], time(10, 0), safety_margin_minutes=30)

        assert result is False

    def test_all_slots_none(self) -> None:
        """All slots have None values → False.

        Technique: Equivalence Partitioning — all-inactive schedule.
        """
        schedule: CycleTimeSchedule = [
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_second_slot_matches(self) -> None:
        """First slot doesn't match, second does → True.

        Technique: Specification-based — any matching slot returns True.
        """
        schedule = _schedule_with_two_windows()

        # 18:00 is within the second window (16:00–22:00)
        result = is_within_heating_window(
            schedule, time(18, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_multiple_windows_first_matches(self) -> None:
        """Two valid windows, now in first → True.

        Technique: Specification-based — early match short-circuits.
        """
        schedule = _schedule_with_two_windows()

        # 08:00 is within the first window (06:00–10:00)
        result = is_within_heating_window(
            schedule, time(8, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_mixed_none_and_valid_slots(self) -> None:
        """Some None slots, one valid matching slot → True.

        Technique: Equivalence Partitioning — interleaved active/inactive.
        """
        schedule: CycleTimeSchedule = [
            [[None, None], [None, None]],
            [[8, 0], [16, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is True

    def test_zero_safety_margin(self) -> None:
        """margin=0, now=13:59, window 06:00–14:00 → True.

        Technique: Boundary Value Analysis — zero margin means the full
        window is usable up to (but not including) the end.
        """
        result = is_within_heating_window(
            _WINDOW_06_14, time(13, 59), safety_margin_minutes=0
        )

        assert result is True

    def test_partially_none_slot_is_skipped(self) -> None:
        """A slot with only hours=None (e.g. [None, 0]) is inactive.

        Technique: Error Guessing — hardware byte 0xF8 decodes as
        [None, 0]; the ``None in slot`` guard must catch partial None.
        """
        schedule: CycleTimeSchedule = [
            [[None, 0], [14, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=30
        )

        assert result is False

    def test_zero_duration_window(self) -> None:
        """Window with start == end is never matchable.

        Technique: Boundary Value Analysis — zero-duration window means
        start <= now < effective_end can never be satisfied.
        """
        schedule: CycleTimeSchedule = [
            [[10, 0], [10, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(10, 0), safety_margin_minutes=0
        )

        assert result is False

    def test_margin_exceeds_window_duration(self) -> None:
        """Window 06:00–06:20, margin=30 → never matchable.

        Technique: Boundary Value Analysis — effective_end becomes negative
        (before start), so the window is skipped.
        """
        schedule: CycleTimeSchedule = [
            [[6, 0], [6, 20]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]

        result = is_within_heating_window(
            schedule, time(6, 10), safety_margin_minutes=30
        )

        assert result is False

    def test_negative_margin_raises(self) -> None:
        """Negative safety margin is a caller bug.

        Technique: Error Guessing — guard against invalid input.
        """
        with pytest.raises(ValueError, match="non-negative"):
            is_within_heating_window(
                _WINDOW_06_14, time(10, 0), safety_margin_minutes=-1
            )


# ===========================================================================
# TIMER_SIGNAL_FOR_DAY
# ===========================================================================


class TestTimerSignalForDay:
    """Tests for the TIMER_SIGNAL_FOR_DAY constant.

    Technique: Cross-reference — mapping must align with the command registry.
    """

    def test_covers_all_seven_days(self) -> None:
        """Dict has exactly 7 entries, keys 0–6.

        Technique: Specification-based — one entry per weekday.
        """
        assert set(TIMER_SIGNAL_FOR_DAY.keys()) == {0, 1, 2, 3, 4, 5, 6}
        assert len(TIMER_SIGNAL_FOR_DAY) == 7

    def test_monday_maps_correctly(self) -> None:
        """0 → 'timer_hw_monday'.

        Technique: Specification-based — spot check.
        """
        assert TIMER_SIGNAL_FOR_DAY[0] == "timer_hw_monday"

    def test_sunday_maps_correctly(self) -> None:
        """6 → 'timer_hw_sunday'.

        Technique: Specification-based — spot check.
        """
        assert TIMER_SIGNAL_FOR_DAY[6] == "timer_hw_sunday"

    @pytest.mark.parametrize("day", range(7), ids=lambda d: f"day_{d}")
    def test_signal_names_match_commands(self, day: int) -> None:
        """All values exist in the COMMANDS registry.

        Technique: Cross-reference — every signal name is a valid command.
        """
        signal_name = TIMER_SIGNAL_FOR_DAY[day]

        assert signal_name in COMMANDS, f"{signal_name!r} not found in COMMANDS"


# ===========================================================================
# Helpers for device state machine tests
# ===========================================================================

# Standard single-window schedule: 06:00–14:00 (reused from above)
_SCHEDULE_06_14: CycleTimeSchedule = [
    [[6, 0], [14, 0]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
    [[None, None], [None, None]],
]

_CMD_TOPIC = "legionella/set"
_CMD_START = json.dumps({"action": "start"})
_CMD_CANCEL = json.dumps({"action": "cancel"})


class _FakeDeviceStore:
    """Minimal dict-backed DeviceStore stand-in for testing.

    Implements the subset of the DeviceStore API used by _legionella_device:
    ``get``, ``update``, ``save``.
    """

    def __init__(self, initial: dict[str, object] | None = None) -> None:
        self._data: dict[str, object] = initial or {}
        self.save_calls: int = 0

    def get(self, key: str, default: object = None) -> object:
        return self._data.get(key, default)

    def update(self, other: dict[str, object] | None = None, **kwargs: object) -> None:
        if other:
            self._data.update(other)
        self._data.update(kwargs)

    def save(self) -> None:
        self.save_calls += 1


class _FakeContext:
    """Lightweight DeviceContext stub with isolated per-instance state.

    Replaces the previous approach of mutating ``type(MagicMock)`` class
    attributes, which leaked between tests (Action 6).

    Parameters:
        port: The OptolinkPort mock returned by ``adapter()``.
        settings: The settings object returned by the ``settings`` property.
        shutdown_after_waits: Number of empty-queue ``asyncio.wait_for``
            timeout cycles (counted by ``_instant_wait_for``) before
            ``shutdown_requested`` flips to ``True``.
    """

    def __init__(
        self,
        port: OptolinkPort | None = None,
        settings: Any = None,
        shutdown_after_waits: int = 1,
    ) -> None:
        self.publish_state = AsyncMock()
        self._port = port or AsyncMock(spec=OptolinkPort)
        self._shutdown_after = shutdown_after_waits
        self._timeout_count = 0
        self._shutdown = False

        if settings is None:
            settings = MagicMock()
            settings.legionella_safety_margin_minutes = 30
            settings.legionella_temperature = 68
            settings.legionella_duration_minutes = 3
        self._settings = settings

        # on_command stores the handler so tests can invoke it
        self._command_handler: Any = None

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown

    @property
    def settings(self) -> Any:
        return self._settings

    def adapter(self, _protocol: type) -> Any:
        return self._port

    def on_command(self, handler: Any) -> Any:
        self._command_handler = handler
        return handler

    def record_timeout(self) -> None:
        """Called by ``_instant_wait_for`` on each TimeoutError."""
        self._timeout_count += 1
        if self._timeout_count >= self._shutdown_after:
            self._shutdown = True


@contextmanager
def _instant_wait_for(ctx: _FakeContext):
    """Patch ``asyncio.wait_for`` in the legionella module for instant timeouts.

    When the awaitable completes in a single event-loop step (e.g. queue
    has an item or an ``AsyncMock`` is awaited), the result is returned
    normally.  Otherwise the task is cancelled, ``TimeoutError`` is
    raised, and a timeout is recorded on the context so that
    ``shutdown_requested`` flips after the configured number of cycles.

    This avoids real 5 s / 60 s waits in tests while preserving the
    Queue-based command dispatch semantics introduced by Action 1.

    **Why not ``timeout=0``?**  CPython's ``wait_for`` with ``timeout<=0``
    cancels the task *before* it runs, so ``queue.get()`` never sees
    available items.  Instead we ``ensure_future`` + ``sleep(0)`` to give
    the task exactly one event-loop iteration, then check ``done()``.
    """

    async def _patched(coro, *, timeout):  # noqa: ANN001, ARG001, ANN202
        task = asyncio.ensure_future(coro)
        # Yield once so the task can run a single step
        await asyncio.sleep(0)
        if task.done():
            return task.result()  # re-raises if the task had an exception
        # Task still pending → simulate instant timeout
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await task
        ctx.record_timeout()
        raise TimeoutError

    with patch("vito2mqtt.devices.legionella.asyncio.wait_for", _patched):
        yield


def _make_inject_start(
    ctx: _FakeContext,
    *,
    cancel_on_heating: bool = False,
) -> Callable[[dict[str, object]], Awaitable[None]]:
    """Factory for ``publish_state`` side-effects that inject commands.

    Injects a ``start`` command on first ``idle`` state.  Optionally
    injects a ``cancel`` command on first ``heating`` state.
    """
    _started = False
    _cancelled = False

    async def _inject(state: dict[str, object]) -> None:
        nonlocal _started, _cancelled
        if state == {"status": "idle"} and not _started:
            _started = True
            await ctx._command_handler(_CMD_TOPIC, _CMD_START)
        elif cancel_on_heating and state.get("status") == "heating" and not _cancelled:
            _cancelled = True
            await ctx._command_handler(_CMD_TOPIC, _CMD_CANCEL)

    return _inject


# ===========================================================================
# _legionella_device — state machine tests
# ===========================================================================


class TestLegionellaDevice:
    """Tests for the _legionella_device async state machine.

    Technique: State Transition Testing — verify transitions between
    idle, checking, heating, restoring, and recovered states.

    Testing pattern:
    1. ``_FakeContext`` is a proper stub class with per-instance shutdown
       state (no ``type(mock)`` mutation leaking between tests).
    2. ``_instant_wait_for`` patches ``asyncio.wait_for`` so empty-queue
       polls resolve instantly as ``TimeoutError``.  After a configurable
       number of timeouts, ``shutdown_requested`` flips.
    3. Commands are injected deterministically via ``publish_state``
       side-effects — when the device publishes a known state, the
       side-effect fires the command *before* the next ``wait_for``,
       ensuring the queue already has an item.
    """

    async def test_startup_recovery_restores_setpoint(self) -> None:
        """Store has active=True + original_setpoint → device restores and
        publishes recovered state.

        Technique: Error Guessing — simulates crash recovery scenario.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)
        store = _FakeDeviceStore(
            {
                _STORE_KEY_ACTIVE: True,
                _STORE_KEY_ORIGINAL_SETPOINT: 50,
            }
        )
        ctx = _FakeContext(port=port, shutdown_after_waits=1)

        # Act
        with _instant_wait_for(ctx):
            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — original setpoint written back
        port.write_signal.assert_any_await(LEGIONELLA_SETPOINT_SIGNAL, 50)

        # Assert — recovered + idle states published
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        assert {"status": "recovered", "original_setpoint": 50} in published
        assert {"status": "idle"} in published

        # Assert — store cleared and saved
        assert store.get(_STORE_KEY_ACTIVE) is False
        assert store.get(_STORE_KEY_ORIGINAL_SETPOINT) is None
        assert store.save_calls >= 1

    async def test_idle_publishes_idle_state(self) -> None:
        """Device publishes idle state on startup when store is clean.

        Technique: Specification-based — verify initial state publication.
        """
        # Arrange
        store = _FakeDeviceStore()
        ctx = _FakeContext(shutdown_after_waits=1)

        # Act
        with _instant_wait_for(ctx):
            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert
        ctx.publish_state.assert_any_await({"status": "idle"})

    async def test_start_checks_heating_window(self) -> None:
        """Start action reads today's timer signal and calls is_within_heating_window.

        Technique: State Transition — idle → checking transition.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)
        port.read_signal = AsyncMock(return_value=_SCHEDULE_06_14)
        store = _FakeDeviceStore()
        ctx = _FakeContext(port=port, shutdown_after_waits=3)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        # Pin datetime to Monday 10:00 (inside heating window)
        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # Monday  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — timer signal for Monday was read
        port.read_signal.assert_any_await("timer_hw_monday")

    async def test_start_rejected_outside_window(self) -> None:
        """Safety check fails → publishes rejected + idle states.

        Technique: State Transition — checking → rejected → idle.
        """
        # Arrange — empty schedule means no valid window
        empty_schedule: CycleTimeSchedule = [
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]
        port = AsyncMock(spec=OptolinkPort)
        port.read_signal = AsyncMock(return_value=empty_schedule)
        store = _FakeDeviceStore()
        ctx = _FakeContext(port=port, shutdown_after_waits=3)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — rejected state published
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        statuses = [p["status"] for p in published]
        assert "rejected" in statuses
        rejected_payload = next(p for p in published if p["status"] == "rejected")
        assert "reason" in rejected_payload

    async def test_start_succeeds_within_window(self) -> None:
        """Safety check passes → writes setpoint, publishes heating.

        Technique: State Transition — checking → heating → restoring → idle.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50  # original setpoint
            return _SCHEDULE_06_14  # timer schedule

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock()
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 2
        ctx = _FakeContext(port=port, shutdown_after_waits=5, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # Monday  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — target temp written
        port.write_signal.assert_any_await(LEGIONELLA_SETPOINT_SIGNAL, 68)

        # Assert — heating state published
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        statuses = [p["status"] for p in published]
        assert "heating" in statuses

        heating_payload = next(p for p in published if p["status"] == "heating")
        assert heating_payload["target_temperature"] == 68
        assert heating_payload["original_setpoint"] == 50

        # Assert — original setpoint restored
        assert port.write_signal.await_count >= 2
        restore_call = port.write_signal.await_args_list[-1]
        assert restore_call == call(LEGIONELLA_SETPOINT_SIGNAL, 50)

        # Assert — restoring + idle published at end
        assert "restoring" in statuses
        assert statuses[-1] == "idle"

    async def test_cancel_restores_immediately(self) -> None:
        """Cancel during heating → immediate restore.

        Technique: State Transition — heating → cancel → restoring → idle.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50
            return _SCHEDULE_06_14

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock()
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 10  # long duration
        ctx = _FakeContext(port=port, shutdown_after_waits=15, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx, cancel_on_heating=True)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — original setpoint restored
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        statuses = [p["status"] for p in published]
        assert "restoring" in statuses

        # Assert — final write is the original setpoint
        restore_call = port.write_signal.await_args_list[-1]
        assert restore_call == call(LEGIONELLA_SETPOINT_SIGNAL, 50)

    async def test_natural_end_restores(self) -> None:
        """Full duration elapses → restore original setpoint.

        Technique: State Transition — heating countdown reaches zero.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50
            return _SCHEDULE_06_14

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock()
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 2  # short duration for test
        ctx = _FakeContext(port=port, shutdown_after_waits=5, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — store cleared
        assert store.get(_STORE_KEY_ACTIVE) is False

        # Assert — restoring + idle published
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        statuses = [p["status"] for p in published]
        assert "restoring" in statuses
        assert statuses[-1] == "idle"

    async def test_publishes_remaining_minutes(self) -> None:
        """During heating, remaining_minutes decrements each minute.

        Technique: Boundary Value Analysis — verify countdown progression.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50
            return _SCHEDULE_06_14

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock()
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 3
        ctx = _FakeContext(port=port, shutdown_after_waits=8, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — heating states have decrementing remaining_minutes
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        heating_payloads = [p for p in published if p.get("status") == "heating"]
        remaining_values = [p["remaining_minutes"] for p in heating_payloads]

        # Should start at 3 and decrement: 3, 2, 1
        assert remaining_values[0] == 3
        assert remaining_values == sorted(remaining_values, reverse=True)
        assert len(remaining_values) >= 2

    async def test_graceful_shutdown_best_effort_restore(self) -> None:
        """Shutdown during heating → best-effort restore attempted.

        Technique: Error Guessing — graceful shutdown should not leave the
        boiler at the elevated temperature.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50
            return _SCHEDULE_06_14

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock()
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 10
        # Shutdown after 2 countdown timeouts so the device exits during
        # heating (the start command fills the queue on the first main-loop
        # wait_for, so only countdown wait_fors count as timeouts).
        ctx = _FakeContext(port=port, shutdown_after_waits=2, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — best-effort restore was attempted: the last write
        # should be the original setpoint (50), not the treatment temp (68)
        last_write = port.write_signal.await_args_list[-1]
        assert last_write == call(LEGIONELLA_SETPOINT_SIGNAL, 50)

        # Assert — store cleared after successful restore
        assert store.get(_STORE_KEY_ACTIVE) is False
        assert store.get(_STORE_KEY_ORIGINAL_SETPOINT) is None

    async def test_graceful_shutdown_restore_failure_preserves_store(
        self,
    ) -> None:
        """Shutdown + write failure → store stays active for crash recovery.

        Technique: Error Guessing — serial timeout during shutdown means
        crash recovery must handle it on next startup.
        """
        # Arrange
        port = AsyncMock(spec=OptolinkPort)
        _write_count = 0

        async def _read_signal(name: str) -> Any:
            if name == LEGIONELLA_SETPOINT_SIGNAL:
                return 50
            return _SCHEDULE_06_14

        async def _write_signal(name: str, value: object) -> None:  # noqa: ARG001
            nonlocal _write_count
            _write_count += 1
            if _write_count > 1:
                # First write (set treatment temp) succeeds.
                # Second write (restore during shutdown) fails.
                msg = "Serial timeout"
                raise OSError(msg)

        port.read_signal = AsyncMock(side_effect=_read_signal)
        port.write_signal = AsyncMock(side_effect=_write_signal)
        store = _FakeDeviceStore()
        settings = MagicMock()
        settings.legionella_safety_margin_minutes = 30
        settings.legionella_temperature = 68
        settings.legionella_duration_minutes = 10
        ctx = _FakeContext(port=port, shutdown_after_waits=2, settings=settings)
        ctx.publish_state.side_effect = _make_inject_start(ctx)

        with (
            patch("vito2mqtt.devices.legionella.datetime") as mock_dt,
            _instant_wait_for(ctx),
        ):
            mock_now = datetime(2026, 3, 2, 10, 0)  # noqa: DTZ001
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Assert — store still active because restore write failed
        assert store.get(_STORE_KEY_ACTIVE) is True
        assert store.get(_STORE_KEY_ORIGINAL_SETPOINT) == 50

    async def test_non_dict_json_rejected(self) -> None:
        """Non-object JSON payloads (arrays, strings) are rejected gracefully.

        Technique: Error Guessing — json.loads accepts arrays and scalars
        which would cause AttributeError on .get() without the guard.
        """
        # Arrange
        store = _FakeDeviceStore()
        ctx = _FakeContext(shutdown_after_waits=1)

        with _instant_wait_for(ctx):
            await _legionella_device(ctx, store)  # type: ignore[arg-type]

        # Now invoke the handler with non-dict JSON — should not raise
        assert ctx._command_handler is not None
        await ctx._command_handler(_CMD_TOPIC, "[]")
        await ctx._command_handler(_CMD_TOPIC, '"just a string"')
        await ctx._command_handler(_CMD_TOPIC, "42")
        await ctx._command_handler(_CMD_TOPIC, "null")

        # No exception means the guard works.  Also verify no state
        # change — only idle was published (no checking/heating/etc.)
        published = [c.args[0] for c in ctx.publish_state.await_args_list]
        statuses = [p["status"] for p in published]
        assert statuses == ["idle"]


# ===========================================================================
# register_legionella
# ===========================================================================


class TestRegisterLegionella:
    """Tests for the register_legionella helper function.

    Technique: Specification-based — verify correct device registration.
    """

    def test_registers_device(self) -> None:
        """Calls app.add_device with 'legionella' name and correct function.

        Technique: Specification-based — registration contract.
        """
        # Arrange
        app = MagicMock()

        # Act
        register_legionella(app)

        # Assert
        app.add_device.assert_called_once_with("legionella", _legionella_device)
