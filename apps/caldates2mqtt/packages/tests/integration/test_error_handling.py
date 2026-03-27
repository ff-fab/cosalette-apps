"""Integration tests for error handling in caldates2mqtt.

Verifies that CalDAV read failures are published as MQTT error messages
and that the application health infrastructure remains alive even when
a device crashes due to an unhandled error.

Note: The calendar device handler does not catch CalDavError — errors
propagate and crash the device. Cosalette catches the crash, publishes
it to the error topic, and keeps the app alive.  Recovery would require
the handler to have its own try/except (a future enhancement).

Test Techniques Used:
- Error Guessing: CalDav*Error during device poll
- Specification-based: error topic structure, app stays alive
"""

from __future__ import annotations

import json

import pytest
from cosalette import MockMqttClient

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.errors import (
    CalDavAuthError,
    CalDavConnectionError,
    CalDavTimeoutError,
)
from caldates2mqtt.settings import CalDates2MqttSettings

from .conftest import TOPIC_PREFIX, build_integration_app, run_app_briefly


# ---------------------------------------------------------------------------
# Error publishing
# ---------------------------------------------------------------------------


class TestErrorPublishing:
    """Verify that CalDAV errors are published to MQTT error topics."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_connection_error_published_to_device_error_topic(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """CalDavConnectionError is published to per-device error topic.

        Technique: Error Guessing — verify error routing through full stack.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavConnectionError("server unreachable")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert — per-device error topic has messages
        error_topic = f"{TOPIC_PREFIX}/garbage/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages, (
            f"Expected error on {error_topic}; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_connection_error_published_to_global_error_topic(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """CalDavConnectionError is also published to the global error topic.

        Technique: Specification-based — global error topic contract.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavConnectionError("server unreachable")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/error")
        assert messages, (
            f"Expected error on {TOPIC_PREFIX}/error; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_auth_error_published_to_error_topic(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """CalDavAuthError is published to the error topic.

        Technique: Error Guessing — auth failure is caught by framework.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavAuthError("invalid credentials")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert
        error_topic = f"{TOPIC_PREFIX}/garbage/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages, f"Expected error on {error_topic}"

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_timeout_error_published_to_error_topic(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """CalDavTimeoutError is published to the error topic.

        Technique: Error Guessing — timeout is caught by framework.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavTimeoutError("request timed out")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert
        error_topic = f"{TOPIC_PREFIX}/garbage/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages, f"Expected error on {error_topic}"

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_error_payload_contains_message(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Error payload is valid JSON containing the error message.

        Technique: Specification-based — error payload structure.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavConnectionError("server unreachable")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert
        error_topic = f"{TOPIC_PREFIX}/garbage/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages
        payload = json.loads(messages[0][0])
        assert "message" in payload
        assert "server unreachable" in payload["message"]


# ---------------------------------------------------------------------------
# App stays alive after device crash
# ---------------------------------------------------------------------------


class TestAppSurvivesDeviceCrash:
    """Verify that the app remains alive after a device crashes."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_status_published_after_device_crash(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """App publishes health status even after a device crashes.

        Technique: State Transition — device crash does not kill the app.
        """
        # Arrange
        fake_reader.raise_on_next = CalDavConnectionError("server unreachable")
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert — health status was published (app stayed alive)
        status_msgs = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        assert status_msgs, "Expected health status after device crash"
