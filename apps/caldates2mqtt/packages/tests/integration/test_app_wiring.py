"""Integration tests for caldates2mqtt full app wiring.

Exercises the real application wiring (startup -> device poll -> MQTT
publish -> shutdown) end-to-end using in-memory test doubles
(FakeCalDavReader, MockMqttClient), with no real CalDAV or MQTT I/O.

Test Techniques Used:
- Integration Testing: Full app wiring through cosalette framework
- Specification-based: MQTT topic structure, payload shape (ISO 8601 dates)
- State Transition Testing: Startup online -> shutdown offline lifecycle
"""

from __future__ import annotations

import json

import pytest
from cosalette import App, MockMqttClient

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.settings import CalDates2MqttSettings

from .conftest import TOPIC_PREFIX, build_integration_app, run_app_briefly

# ---------------------------------------------------------------------------
# Startup and health
# ---------------------------------------------------------------------------


class TestAppStartup:
    """Verify that the app boots and publishes health status."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_online_published_on_startup(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Technique: Integration — verify cosalette health reporter fires.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        assert messages, f"Expected at least one message on {TOPIC_PREFIX}/status"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("online" in p or "available" in p for p in payloads), (
            f"No 'online'/'available' payload found; got: {payloads}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Health status contains 'offline' payload after clean shutdown.

        Technique: State Transition — startup -> shutdown lifecycle.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("offline" in p or "unavailable" in p for p in payloads), (
            f"No 'offline'/'unavailable' payload found; got: {payloads}"
        )


# ---------------------------------------------------------------------------
# Telemetry publishing
# ---------------------------------------------------------------------------


class TestTelemetryPublishing:
    """Verify that calendar events are published to the correct topics."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_calendar_state_published_after_first_cycle(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Device publishes calendar events to per-device state topic.

        Technique: Integration — verify full pipeline from FakeCalDavReader to MQTT.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert messages, (
            f"Expected state on {state_topic}; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

        payload = json.loads(messages[0][0])
        assert isinstance(payload, dict)
        assert "events" in payload
        assert isinstance(payload["events"], list)
        assert len(payload["events"]) > 0

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_payload_has_iso_8601_dates_and_sorted_events(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Published events have ISO 8601 date strings and are date-sorted.

        Technique: Specification-based — verify payload contract.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert messages
        payload = json.loads(messages[0][0])
        events = payload["events"]

        # Each event has title and ISO 8601 date
        for event in events:
            assert "title" in event
            assert "date" in event
            # ISO 8601 date format: YYYY-MM-DD
            assert len(event["date"]) == 10
            assert event["date"][4] == "-"
            assert event["date"][7] == "-"

        # Events are sorted by date
        dates = [e["date"] for e in events]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


class TestAvailability:
    """Verify availability messages on startup and shutdown."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_availability_online_on_start(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Device availability published as 'online' on startup.

        Technique: Specification-based — verify cosalette availability wiring.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        avail_topic = f"{TOPIC_PREFIX}/garbage/availability"
        messages = mock_mqtt.get_messages_for(avail_topic)
        assert messages, (
            f"Expected availability on {avail_topic}; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("online" in p for p in payloads), (
            f"No 'online' availability found; got: {payloads}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_availability_offline_on_shutdown(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Device availability published as 'offline' on graceful shutdown.

        Technique: State Transition — verify offline published on shutdown.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        avail_topic = f"{TOPIC_PREFIX}/garbage/availability"
        messages = mock_mqtt.get_messages_for(avail_topic)
        assert messages, f"Expected availability on {avail_topic}"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("offline" in p for p in payloads), (
            f"No 'offline' availability found; got: {payloads}"
        )


# ---------------------------------------------------------------------------
# Multi-calendar
# ---------------------------------------------------------------------------


class TestMultiCalendar:
    """Verify that multiple calendars each get their own MQTT topics."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_each_calendar_publishes_to_own_state_topic(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        multi_calendar_settings: CalDates2MqttSettings,
    ) -> None:
        """Each configured calendar publishes state to its own topic.

        Technique: Integration — verify dynamic multi-device registration.
        """
        # Arrange
        app = build_integration_app(fake_reader)

        # Act
        await run_app_briefly(app, mock_mqtt, multi_calendar_settings)

        # Assert — both calendars published state
        for key in ("garbage", "holidays"):
            state_topic = f"{TOPIC_PREFIX}/{key}/state"
            messages = mock_mqtt.get_messages_for(state_topic)
            assert messages, (
                f"Expected state on {state_topic}; "
                f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
            )
