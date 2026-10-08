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

"""Integration tests for the per-group telemetry freshness policy.

With every polling interval at 10 s, cosalette derives ``stale_after`` for each
group as ``2 x 10 + 10 x 4 + 72 x 3 = 276 s`` (ADR-080: the implicit timeout
equals the interval, ``retry=3``, and the default backoff allows 72 s per
retry). The freshness watchdog checks every 60 s, so a group that stops
answering at t=0 turns ``"stale"`` at the 300 s check.

vito2mqtt sets neither ``exit_after_stale`` nor ``restart_on_stale``: a stale
group is reported, not acted on, and the healthy groups keep publishing.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the derived bound
- State Transition: ok -> error -> stale, with the app still running
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import pytest
from cosalette.testing import AppHarness, ManualClock

from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices import SIGNAL_GROUPS
from vito2mqtt.errors import OptolinkConnectionError

from .conftest import TOPIC_PREFIX, make_harness

_INTERVAL = 10
_DERIVED_STALE_AFTER = 2 * _INTERVAL + _INTERVAL * 4 + 72 * 3
"""The derived per-group bound for ``_INTERVAL``; see module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = (_DERIVED_STALE_AFTER // _CHECK_INTERVAL + 1) * _CHECK_INTERVAL
"""The first watchdog check past the derived bound."""

_STATUS_TOPIC = f"{TOPIC_PREFIX}/status"


class _DeadOutdoorAdapter(FakeOptolinkAdapter):
    """Fake adapter whose outdoor sensors stop answering once ``dead`` is set."""

    _OUTDOOR = frozenset(SIGNAL_GROUPS["outdoor"])
    dead = False

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        if self.dead and self._OUTDOOR.intersection(names):
            msg = "no answer from boiler"
            raise OptolinkConnectionError(msg)
        return await super().read_signals(names)


def _statuses(harness: AppHarness) -> dict[str, str]:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    devices = json.loads(payload)["devices"]
    return {group: devices[group]["status"] for group in SIGNAL_GROUPS}


@pytest.mark.integration
async def test_dead_group_goes_stale_while_others_stay_ok() -> None:
    """A group that stops answering turns stale; the app keeps running.

    Technique: Boundary Value Analysis — one check before the derived bound
    the outdoor group is only ``error``; after the first check past it the
    heartbeat reports ``stale``. Every other group stays ``ok`` and the app
    does not exit, because no stale exit or restart policy is set.
    """
    adapter = _DeadOutdoorAdapter()
    harness = make_harness(
        adapter,
        clock=ManualClock(),
        settings=Vito2MqttSettings(
            serial_port="/dev/ttyUSB0",
            **{f"polling_{g}": _INTERVAL for g in SIGNAL_GROUPS},
        ),
    )
    elapsed = 0

    async def advance_to(target: int) -> None:
        # One second at a time, so every poll, retry and backoff runs.
        nonlocal elapsed
        while elapsed < target:
            await harness.advance_time(1)
            elapsed += 1

    task = asyncio.create_task(harness.run())
    try:
        await harness.wait_for_publish_count(_STATUS_TOPIC, 1)
        await harness.advance_time(0)
        adapter.dead = True

        await advance_to(_DERIVED_STALE_AFTER - _CHECK_INTERVAL)
        statuses = _statuses(harness)
        assert statuses.pop("outdoor") == "error"
        assert set(statuses.values()) == {"ok"}

        await advance_to(_STALE_AT + _CHECK_INTERVAL)
        statuses = _statuses(harness)
        assert statuses.pop("outdoor") == "stale"
        assert set(statuses.values()) == {"ok"}
        assert not task.done()
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
