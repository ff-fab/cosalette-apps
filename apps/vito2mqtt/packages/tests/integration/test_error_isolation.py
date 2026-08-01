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

"""Integration tests for error isolation and fault tolerance.

Verifies that adapter read failures are published as MQTT error messages,
that the application continues running when one or more telemetry groups
fail, and that per-group errors do not prevent healthy groups from
publishing telemetry.

Test Techniques Used
--------------------
- **Error Guessing**: adapter raises ``RuntimeError`` on every read,
  covering the worst-case scenario of total adapter failure.
- **State Transition**: app transitions through error states but stays
  alive and responsive — other groups keep polling (ADR-004).
- **Specification-based**: error topics follow the ADR-002 contract:
  ``vito2mqtt/error`` (global) and ``vito2mqtt/{group}/error`` (per-group).
- **Partial failure**: a partially-broken adapter verifies that healthy
  groups publish normally while the broken group publishes errors.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import pytest
from cosalette.testing import AppHarness

from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.devices import SIGNAL_GROUPS

from .conftest import TOPIC_PREFIX, make_harness, run_app_briefly

# ---------------------------------------------------------------------------
# Test adapter subclasses
# ---------------------------------------------------------------------------


class _RaisingAdapter(FakeOptolinkAdapter):
    """FakeOptolinkAdapter that raises RuntimeError on every read."""

    async def read_signal(self, name: str) -> Any:
        msg = f"Simulated read failure for {name!r}"
        raise RuntimeError(msg)

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        msg = "Simulated batch read failure"
        raise RuntimeError(msg)


class _PartiallyRaisingAdapter(FakeOptolinkAdapter):
    """FakeOptolinkAdapter that fails only for the 'outdoor' signal group.

    All other groups read normally via the parent implementation.
    """

    _OUTDOOR_NAMES: frozenset[str] = frozenset(SIGNAL_GROUPS.get("outdoor", ()))

    async def read_signal(self, name: str) -> Any:
        if name in self._OUTDOOR_NAMES:
            msg = f"Outdoor sensor failure: {name!r}"
            raise RuntimeError(msg)
        return await super().read_signal(name)

    async def read_signals(self, names: Sequence[str]) -> dict[str, Any]:
        if any(n in self._OUTDOOR_NAMES for n in names):
            msg = "Outdoor batch read failure"
            raise RuntimeError(msg)
        return await super().read_signals(names)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def raising_adapter() -> _RaisingAdapter:
    """An adapter that raises RuntimeError on every read."""
    return _RaisingAdapter()


@pytest.fixture
def raising_harness(raising_adapter: _RaisingAdapter) -> AppHarness:
    """A fully-wired AppHarness whose adapter always raises on reads."""
    return make_harness(raising_adapter)


@pytest.fixture
def partial_adapter() -> _PartiallyRaisingAdapter:
    """An adapter that raises only for outdoor group reads."""
    return _PartiallyRaisingAdapter()


@pytest.fixture
def partial_harness(partial_adapter: _PartiallyRaisingAdapter) -> AppHarness:
    """A fully-wired AppHarness whose adapter raises only for the outdoor group."""
    return make_harness(partial_adapter)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_any_group_error(harness: AppHarness) -> bool:
    """Return True if any per-group error topic has messages."""
    groups = [
        "outdoor",
        "hot_water",
        "burner",
        "heating_radiator",
        "heating_floor",
        "system",
    ]
    return any(
        harness.mqtt.get_messages_for(f"{TOPIC_PREFIX}/{g}/error") for g in groups
    )


def _has_non_outdoor_state(harness: AppHarness) -> bool:
    """Return True if any non-outdoor state topic has messages."""
    groups = ["hot_water", "burner", "heating_radiator", "heating_floor", "system"]
    return any(
        harness.mqtt.get_messages_for(f"{TOPIC_PREFIX}/{g}/state") for g in groups
    )


# ---------------------------------------------------------------------------
# TestTelemetryErrorPublishing
# ---------------------------------------------------------------------------


class TestTelemetryErrorPublishing:
    """Error messages are published on MQTT when the adapter raises."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_adapter_read_error_publishes_to_error_topic(
        self,
        raising_harness: AppHarness,
    ) -> None:
        """A global error message appears on ``vito2mqtt/error`` after adapter failure.

        Arrange: App wired with _RaisingAdapter (every read raises).
        Act: run for 0.4 s (≥ 8 polling ticks at 0.05 s).
        Assert: at least one message published on ``vito2mqtt/error``.

        Specification-based: follows the ADR-002 error topic contract.
        """
        # Act
        await run_app_briefly(raising_harness, wait=0.4)

        # Assert
        raising_harness.assert_published(f"{TOPIC_PREFIX}/error")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_adapter_read_error_publishes_to_group_error_topic(
        self,
        raising_harness: AppHarness,
    ) -> None:
        """Per-group error topics receive messages when the adapter raises.

        Arrange: App wired with _RaisingAdapter.
        Act: run for 0.4 s.
        Assert: at least one ``vito2mqtt/{group}/error`` topic has messages.

        Specification-based: per-group error topics are mandated by ADR-002.
        """
        # Act
        await run_app_briefly(raising_harness, wait=0.4)

        # Assert
        assert _has_any_group_error(raising_harness), (
            "Expected at least one per-group error topic to have messages; "
            f"published topics: "
            f"{sorted({t for t, *_ in raising_harness.mqtt.published})}"
        )


# ---------------------------------------------------------------------------
# TestAppSurvival
# ---------------------------------------------------------------------------


class TestAppSurvival:
    """App continues running and shuts down cleanly despite repeated errors."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_app_survives_repeated_adapter_errors(
        self,
        raising_harness: AppHarness,
    ) -> None:
        """App keeps running when every adapter read raises RuntimeError.

        Arrange: App wired with _RaisingAdapter.
        Act: run for 0.4 s, then shut down.
        Assert: shutdown completes without exception AND the app still
        published at least one health/status message (it ran).

        State Transition: error state does not cause the app to exit early.
        """
        # Act
        await run_app_briefly(raising_harness, wait=0.4)

        # Assert — app published at least one status message (it ran)
        raising_harness.assert_published(f"{TOPIC_PREFIX}/status")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_shutdown_completes_promptly_despite_adapter_errors(
        self,
        raising_harness: AppHarness,
    ) -> None:
        """Shutdown completes promptly even when the adapter keeps raising.

        Arrange: App wired with _RaisingAdapter.
        Act: run for 0.2 s, set shutdown_event, await the task with a 3 s
        timeout.
        Assert: asyncio.wait_for completes without TimeoutError — no deadlock.

        Error Guessing: ensures that error-handling paths release all locks
        and do not spin-wait forever.
        """
        # Arrange
        task = asyncio.create_task(raising_harness.run())

        # Act
        await asyncio.sleep(0.2)
        raising_harness.shutdown_event.set()

        # Assert — must complete within 3 s (no deadlock)
        await asyncio.wait_for(task, timeout=3.0)


# ---------------------------------------------------------------------------
# TestErrorIsolation
# ---------------------------------------------------------------------------


class TestErrorIsolation:
    """Per-group errors do not suppress telemetry from healthy groups."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_healthy_telemetry_publishes_despite_one_raising_adapter(
        self,
        partial_harness: AppHarness,
    ) -> None:
        """Non-outdoor groups publish state while outdoor publishes errors.

        Arrange: App wired with _PartiallyRaisingAdapter (outdoor fails,
        others succeed).
        Act: run for 0.4 s.
        Assert outdoor error: ``vito2mqtt/outdoor/error`` has messages.
        Assert isolation: at least one ``vito2mqtt/*/state`` topic for a
        non-outdoor group has messages — healthy groups are unaffected.

        Error Guessing + State Transition: single-group failure is isolated.
        """
        # Act
        await run_app_briefly(partial_harness, wait=0.4)

        # Assert — outdoor group published errors
        partial_harness.assert_published(f"{TOPIC_PREFIX}/outdoor/error")

        # Assert — non-outdoor groups published state (error isolation)
        assert _has_non_outdoor_state(partial_harness), (
            "Expected at least one non-outdoor */state topic; got "
            f"published topics: "
            f"{sorted({t for t, *_ in partial_harness.mqtt.published})}"
        )
