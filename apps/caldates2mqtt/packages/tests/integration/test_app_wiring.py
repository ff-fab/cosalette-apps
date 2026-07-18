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
from cosalette.testing import AppHarness

from .conftest import TOPIC_PREFIX, run_app_briefly


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _first_state_events(harness: AppHarness, device_key: str) -> list[dict]:
    """Return the events list from the first state message for *device_key*.

    Uses ``get_messages_for`` + ``json.loads`` to extract the payload dict.
    Kept in this helper so test bodies remain free of raw MQTT scanning.
    """
    state_topic = f"{TOPIC_PREFIX}/{device_key}/state"
    messages = harness.mqtt.get_messages_for(state_topic)
    assert messages, f"No state messages on {state_topic}"
    return json.loads(messages[0][0])["events"]


# ---------------------------------------------------------------------------
# Startup and health
# ---------------------------------------------------------------------------


class TestAppStartup:
    """Verify that the app boots and publishes health status."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_online_published_on_startup(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Technique: Integration — verify cosalette health reporter fires.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="online")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status contains 'offline' payload after clean shutdown.

        Technique: State Transition — startup -> shutdown lifecycle.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="offline")


# ---------------------------------------------------------------------------
# Telemetry publishing
# ---------------------------------------------------------------------------


class TestTelemetryPublishing:
    """Verify that calendar events are published to the correct topics."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_calendar_state_published_after_first_cycle(
        self,
        harness: AppHarness,
    ) -> None:
        """Device publishes calendar events to per-device state topic.

        Technique: Integration — verify full pipeline from FakeCalDavReader to MQTT.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — state published as a JSON dict with a non-empty events list
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        harness.assert_state(state_topic, {})
        harness.assert_published(state_topic, contains='"events"')
        harness.assert_published(state_topic, contains='"title"')

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_payload_has_iso_8601_dates_and_sorted_events(
        self,
        harness: AppHarness,
    ) -> None:
        """Published events have ISO 8601 date strings and are date-sorted.

        Technique: Specification-based — verify payload contract.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — structural validation delegated to helper (no raw MQTT in body)
        events = _first_state_events(harness, "garbage")

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
        harness: AppHarness,
    ) -> None:
        """Device availability published as 'online' on startup.

        Technique: Specification-based — verify cosalette availability wiring.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(
            f"{TOPIC_PREFIX}/garbage/availability", contains="online"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_availability_offline_on_shutdown(
        self,
        harness: AppHarness,
    ) -> None:
        """Device availability published as 'offline' on graceful shutdown.

        Technique: State Transition — verify offline published on shutdown.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(
            f"{TOPIC_PREFIX}/garbage/availability", contains="offline"
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
        multi_calendar_harness: AppHarness,
    ) -> None:
        """Each configured calendar publishes state to its own topic.

        Technique: Integration — verify dynamic multi-device registration.
        """
        # Act
        await run_app_briefly(multi_calendar_harness)

        # Assert — both calendars published state
        for key in ("garbage", "holidays"):
            multi_calendar_harness.assert_published(f"{TOPIC_PREFIX}/{key}/state")
