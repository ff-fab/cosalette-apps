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

"""Integration tests for the full application lifecycle.

Exercises the real application wiring (startup → telemetry polling →
shutdown) end-to-end using in-memory test doubles, with no real serial
or MQTT I/O.

Test Techniques Used
--------------------
- **Background task pattern**: Each test starts the AppHarness as a
  background task via ``run_app_briefly``, then triggers a clean shutdown.
- **Time boxing**: ``asyncio.sleep(0.3)`` gives the app enough cycles
  to produce observable output given 0.05 s polling intervals.
- **Test doubles**: ``FakeOptolinkAdapter`` (returns zero-value
  defaults), ``MockMqttClient`` (records all publishes),
  ``MemoryStore`` (no filesystem).
- **AAA pattern**: Each test follows Arrange → Act → Assert.
"""

from __future__ import annotations

import pytest
from cosalette.testing import AppHarness

from .conftest import TOPIC_PREFIX, run_app_briefly

# ---------------------------------------------------------------------------
# TestAppStartup
# ---------------------------------------------------------------------------


class TestAppStartup:
    """Verify that the app publishes its health status on startup."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_online_published_on_startup(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Arrange: fresh App wired with FakeOptolinkAdapter + MockMqttClient.
        Act: run the app for 0.3 s then shut it down.
        Assert: at least one message on ``vito2mqtt/status`` whose payload
        contains "online".
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="online")


# ---------------------------------------------------------------------------
# TestTelemetryPublishing
# ---------------------------------------------------------------------------


class TestTelemetryPublishing:
    """Verify that telemetry messages are published on schedule."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_outdoor_telemetry_published_on_tick(
        self,
        harness: AppHarness,
    ) -> None:
        """At least one outdoor/state message is published within 0.3 s.

        With polling_outdoor=0.05 s the app should tick ~6 times before
        the shutdown event fires.

        Arrange: app wired with FakeOptolinkAdapter.
        Act: run for 0.3 s.
        Assert: a message on ``vito2mqtt/outdoor/state`` appears.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/outdoor/state")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_multiple_groups_published(
        self,
        harness: AppHarness,
    ) -> None:
        """Both outdoor and burner telemetry groups are published.

        Verify that the coalescing group mechanism does not suppress
        any registered signal group from reaching MQTT.

        Arrange: app with all polling intervals at 0.05 s.
        Act: run for 0.3 s.
        Assert: topics containing 'outdoor' AND topics containing 'burner'
        both appear.
        """
        # Act
        await run_app_briefly(harness)

        # outdoor group
        harness.assert_published(f"{TOPIC_PREFIX}/outdoor/state")

        # burner group
        harness.assert_published(f"{TOPIC_PREFIX}/burner/state")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_payload_is_json_parseable(
        self,
        harness: AppHarness,
    ) -> None:
        """Telemetry payloads are valid JSON objects.

        The serialization layer (ADR-006) must produce valid JSON so
        downstream consumers can reliably parse readings.

        Arrange: app with ultra-short polling.
        Act: run for 0.3 s.
        Assert: the outdoor/state topic has a message whose payload is a
        JSON object (dict).
        """
        # Act
        await run_app_briefly(harness)

        # Assert — assert_state verifies the payload is a parseable JSON dict
        harness.assert_state(f"{TOPIC_PREFIX}/outdoor/state", {})


# ---------------------------------------------------------------------------
# TestAppShutdown
# ---------------------------------------------------------------------------


class TestAppShutdown:
    """Verify that the app publishes its health status on clean shutdown."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status topic contains an 'offline' payload after shutdown.

        The app should publish an 'offline' payload AFTER the shutdown event
        fires so subscribers know the bridge has disconnected.

        Arrange: fresh app instance.
        Act: run for 0.3 s then set the shutdown event.
        Assert: among all ``vito2mqtt/status`` messages, at least one
        contains 'offline'.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="offline")
