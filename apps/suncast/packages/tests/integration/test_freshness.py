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

"""Integration tests for the shadow telemetry's freshness policy.

With the default 360 s ``poll_interval`` and its implicit timeout of the same
length, cosalette derives ``stale_after = 2 x 360 + 360 = 1080 s`` (ADR-080,
``retry=0``): three missed cycles. The freshness watchdog checks every 60 s.

A cycle is fresh when the handler returns. Output delivery is best effort: a
failed file write or MQTT publish is logged and the cycle still counts. Only a
handler that keeps raising turns ``shadow`` stale and offline. suncast sets no
``exit_after_stale``, so the process keeps running and keeps serving the last
image.

Test Techniques Used:
- Boundary Value Analysis: one check before and after the derived bound
- Equivalence Partitioning: failed delivery vs failed computation
- State Transition: ok -> error -> stale, with the app still running
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, ManualClock

from suncast import app as app_module
from suncast.settings import SuncastSettings

_POLL_INTERVAL = SuncastSettings.model_fields["poll_interval"].default
_DERIVED_STALE_AFTER = int(3 * _POLL_INTERVAL)
"""The derived bound for the default poll interval; see module docstring."""

_CHECK_INTERVAL = 60
"""The freshness watchdog's check cadence: min(heartbeat, 60 s, stale_after)."""

_STALE_AT = (_DERIVED_STALE_AFTER // _CHECK_INTERVAL + 1) * _CHECK_INTERVAL
"""The first watchdog check past the derived bound."""

_STATUS_TOPIC = "suncast/status"
_AVAILABILITY_TOPIC = "suncast/shadow/availability"
_GEOMETRY = Path(__file__).parents[3] / "geometry.example.yaml"


def _shadow_status(harness: AppHarness) -> str:
    payload = harness.messages_for(_STATUS_TOPIC)[-1][0]
    return json.loads(payload)["devices"]["shadow"]["status"]


async def _run(
    output_path: Path, target: int
) -> tuple[AppHarness, asyncio.Task[None], list[str]]:
    """Run the app to *target* seconds; return the status at each check."""
    harness = AppHarness(
        app=app_module.app,
        mqtt=MockMqttClient(),
        clock=ManualClock(),
        settings=SuncastSettings(
            latitude=47.3769,
            longitude=8.5417,
            timezone="Europe/Zurich",
            geometry_file=_GEOMETRY,
            output_path=output_path,
            mqtt={"tls": False},  # type: ignore[arg-type]
        ),
        shutdown_event=asyncio.Event(),
    )
    task = asyncio.create_task(harness.run())
    await harness.wait_for_publish_count(_STATUS_TOPIC, 1)
    statuses = []
    for _ in range(target // _CHECK_INTERVAL):
        await harness.advance_time(_CHECK_INTERVAL)
        statuses.append(_shadow_status(harness))
    return harness, task, statuses


async def _stop(harness: AppHarness, task: asyncio.Task[None]) -> None:
    harness.shutdown_event.set()
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _run_inline[T](
    func: Callable[..., T], /, *args: object, **kwargs: object
) -> T:
    """Stand-in for :func:`asyncio.to_thread` that runs *func* on the loop."""
    return func(*args, **kwargs)


@pytest.mark.integration
async def test_failed_delivery_keeps_shadow_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An unwritable output path is logged, not a stale entity.

    Technique: Equivalence Partitioning — the delivery-failure partition. The
    output path is a regular file, so every write fails, yet well past the
    derived bound the heartbeat reports ``ok`` at every check.

    Delivery writes in a worker thread, whose real-time completion
    ``ManualClock.advance`` cannot observe. Under CPU load virtual time outran
    the write, the implicit timeout cancelled the cycles and ``shadow`` went
    ``stale``. Running the write inline keeps the failure and drops the race.
    """
    monkeypatch.setattr(asyncio, "to_thread", _run_inline)
    # The framework replaces root logging handlers at startup.
    output_logger = logging.getLogger("suncast.output")
    monkeypatch.setattr(
        output_logger, "handlers", [*output_logger.handlers, caplog.handler]
    )
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")

    harness, task, statuses = await _run(blocked, 2 * _STALE_AT)
    try:
        assert set(statuses) == {"ok"}
        assert not task.done()
        assert any(
            record.name == "suncast.output"
            and record.levelno == logging.WARNING
            and record.getMessage().startswith(
                f"Failed to write {blocked / 'shadow.svg'}:"
            )
            for record in caplog.records
        )
    finally:
        await _stop(harness, task)


@pytest.mark.integration
async def test_failing_computation_goes_stale_and_offline_without_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A handler that keeps raising turns ``shadow`` stale after 1080 s.

    Technique: Boundary Value Analysis — at the last check before the bound
    the entity is only ``error``; at the first check past it the heartbeat
    reports ``stale`` and availability goes ``offline``. The app keeps running.
    """

    def broken(*_args: object) -> object:
        msg = "unexpected computation bug"
        raise RuntimeError(msg)

    monkeypatch.setattr(app_module, "compute_solar_position", broken)

    harness, task, statuses = await _run(tmp_path, _STALE_AT)
    try:
        assert statuses[_DERIVED_STALE_AFTER // _CHECK_INTERVAL - 1] == "error"
        assert statuses[-1] == "stale"
        assert harness.messages_for(_AVAILABILITY_TOPIC)[-1][0] == "offline"
        assert not task.done()
    finally:
        await _stop(harness, task)
