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
- **Background task pattern**: Each test starts ``_run_async`` via
  ``asyncio.create_task()``, allowing the test body to observe
  side-effects while the app runs, then triggers a clean shutdown.
- **Time boxing**: ``asyncio.sleep(0.3)`` gives the app enough cycles
  to produce observable output given 0.05 s polling intervals.
- **Test doubles**: ``FakeOptolinkAdapter`` (returns zero-value
  defaults), ``MockMqttClient`` (records all publishes),
  ``MemoryStore`` (no filesystem).
- **AAA pattern**: Each test follows Arrange → Act → Assert.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette import App, MockMqttClient

from vito2mqtt.config import Vito2MqttSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_app_briefly(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Vito2MqttSettings,
    *,
    wait: float = 0.3,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly.

    Returns after the background task has completed so callers can
    safely inspect ``mock_mqtt.published``.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(wait)
    shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# TestAppStartup
# ---------------------------------------------------------------------------


class TestAppStartup:
    """Verify that the app publishes its health status on startup."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_online_published_on_startup(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Arrange: fresh App wired with FakeOptolinkAdapter + MockMqttClient.
        Act: run the app for 0.3 s then shut it down.
        Assert: at least one message on ``vito2mqtt/status`` whose payload
        contains the word "online" (or "available" — cosalette variant).
        """
        # Act
        await _run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for("vito2mqtt/status")
        assert messages, "Expected at least one message on vito2mqtt/status"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("online" in p or "available" in p for p in payloads), (
            f"No 'online'/'available' payload found; got: {payloads}"
        )


# ---------------------------------------------------------------------------
# TestTelemetryPublishing
# ---------------------------------------------------------------------------


class TestTelemetryPublishing:
    """Verify that telemetry messages are published on schedule."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_outdoor_telemetry_published_on_tick(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
    ) -> None:
        """At least one outdoor/state message is published within 0.3 s.

        With polling_outdoor=0.05 s the app should tick ~6 times before
        the shutdown event fires.

        Arrange: app wired with FakeOptolinkAdapter.
        Act: run for 0.3 s.
        Assert: a topic matching ``*outdoor*state*`` appears in published.
        """
        # Act
        await _run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        outdoor_state_msgs = [
            (topic, payload)
            for topic, payload, _retain, _qos in mock_mqtt.published
            if "outdoor" in topic and "state" in topic
        ]
        assert outdoor_state_msgs, (
            "Expected at least one outdoor/state message; "
            f"published topics: {[t for t, *_ in mock_mqtt.published]}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_multiple_groups_published(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
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
        await _run_app_briefly(integration_app, mock_mqtt, test_settings)

        published_topics = {topic for topic, *_ in mock_mqtt.published}

        # outdoor group
        outdoor_topics = {t for t in published_topics if "outdoor" in t}
        assert outdoor_topics, (
            f"No outdoor topic published; got: {sorted(published_topics)}"
        )

        # burner group
        burner_topics = {t for t in published_topics if "burner" in t}
        assert burner_topics, (
            f"No burner topic published; got: {sorted(published_topics)}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_payload_is_json_parseable(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
    ) -> None:
        """Telemetry payloads are valid JSON objects.

        The serialization layer (ADR-006) must produce valid JSON so
        downstream consumers can reliably parse readings.

        Arrange: app with ultra-short polling.
        Act: run for 0.3 s.
        Assert: the first outdoor/state payload parses as a JSON object (dict).
        """
        # Act
        await _run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Find first outdoor/state message
        outdoor_msgs = [
            (topic, payload)
            for topic, payload, _retain, _qos in mock_mqtt.published
            if "outdoor" in topic and "state" in topic
        ]
        assert outdoor_msgs, "No outdoor/state message found to validate JSON"

        _topic, payload = outdoor_msgs[0]
        parsed = json.loads(payload)
        assert isinstance(parsed, dict), (
            f"Expected JSON object, got {type(parsed).__name__}: {payload!r}"
        )


# ---------------------------------------------------------------------------
# TestAppShutdown
# ---------------------------------------------------------------------------


class TestAppShutdown:
    """Verify that the app publishes its health status on clean shutdown."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Vito2MqttSettings,
    ) -> None:
        """Health status topic contains an 'offline' payload after shutdown.

        The app should publish an 'offline' (or 'unavailable') payload
        AFTER the shutdown event fires so subscribers know the bridge
        has disconnected.

        Arrange: fresh app instance.
        Act: run for 0.3 s then set the shutdown event.
        Assert: among all ``vito2mqtt/status`` messages, at least one
        contains 'offline' or 'unavailable'.
        """
        # Act
        await _run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for("vito2mqtt/status")
        assert messages, "Expected at least one message on vito2mqtt/status"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("offline" in p or "unavailable" in p for p in payloads), (
            f"No 'offline'/'unavailable' payload found; got: {payloads}"
        )
