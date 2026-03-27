"""Integration tests for re-read command dispatch in caldates2mqtt.

Exercises the full command path: MQTT inbound -> TopicRouter -> device
command handler -> FakeCalDavReader.read_events -> MQTT state publish,
using the real application wiring with in-memory test doubles.

Test Techniques Used:
- Integration Testing: Full command dispatch through cosalette framework
- Specification-based: Command payload parsing (empty, JSON overrides, invalid)
- Error Guessing: Invalid JSON payload falls back to defaults
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import App, MockMqttClient

from caldates2mqtt.adapters.fake import FakeCalDavReader
from caldates2mqtt.settings import CalDates2MqttSettings

from .conftest import TOPIC_PREFIX, build_integration_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run_with_command(
    app: App,
    mock_mqtt: MockMqttClient,
    test_settings: CalDates2MqttSettings,
    command_topic: str,
    command_payload: str,
    *,
    startup_wait: float = 0.3,
    post_command_wait: float = 0.2,
) -> None:
    """Start the app, deliver a command, then shut down cleanly.

    Args:
        app: Fully-wired App instance.
        mock_mqtt: MockMqttClient to use for MQTT I/O.
        test_settings: Settings with short polling intervals.
        command_topic: MQTT topic to deliver the command on.
        command_payload: Command payload string.
        startup_wait: Seconds to wait after startup before delivering.
        post_command_wait: Seconds to wait after command before shutdown.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(startup_wait)
    await mock_mqtt.deliver(command_topic, command_payload)
    await asyncio.sleep(post_command_wait)
    shutdown_event.set()
    await task


# ---------------------------------------------------------------------------
# Command dispatch tests
# ---------------------------------------------------------------------------


class TestReReadCommand:
    """Verify re-read command triggers a fresh CalDAV read and publishes state."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_empty_payload_triggers_reread_with_defaults(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Empty payload command triggers re-read using configured defaults.

        Technique: Integration — verify command wiring through full stack.
        """
        # Arrange
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act — send empty command after initial poll has published
        await _run_with_command(
            app,
            mock_mqtt,
            test_settings,
            f"{TOPIC_PREFIX}/garbage/set",
            "",
        )

        # Assert — state was published (at least initial poll + command re-read)
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert len(messages) >= 2, (
            f"Expected at least 2 state publishes (initial + command); "
            f"got {len(messages)} on {state_topic}"
        )

        # Assert — re-read used configured days (14)
        assert fake_reader.calls[-1][4] == 14

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_json_overrides_applied_to_reread(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """JSON payload with entries and days overrides the re-read parameters.

        Technique: Specification-based — command payload contract.
        """
        # Arrange
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await _run_with_command(
            app,
            mock_mqtt,
            test_settings,
            f"{TOPIC_PREFIX}/garbage/set",
            '{"entries": 1, "days": 7}',
        )

        # Assert — at least one read used the overridden days=7
        days_used = [call[4] for call in fake_reader.calls]
        assert 7 in days_used, (
            f"Expected at least one read with days=7; got days: {days_used}"
        )

        # Assert — state was published multiple times (initial + command)
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert len(messages) >= 2, (
            f"Expected at least 2 state publishes; got {len(messages)}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_invalid_json_falls_back_to_defaults(
        self,
        fake_reader: FakeCalDavReader,
        mock_mqtt: MockMqttClient,
        test_settings: CalDates2MqttSettings,
    ) -> None:
        """Invalid JSON command payload falls back to configured defaults.

        Technique: Error Guessing — malformed payload does not crash device.
        """
        # Arrange
        app = build_integration_app(fake_reader, test_settings.calendars)

        # Act
        await _run_with_command(
            app,
            mock_mqtt,
            test_settings,
            f"{TOPIC_PREFIX}/garbage/set",
            "not-valid-json",
        )

        # Assert — state was still published (command used defaults)
        state_topic = f"{TOPIC_PREFIX}/garbage/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert len(messages) >= 2, (
            f"Expected at least 2 state publishes; got {len(messages)}"
        )

        # Assert — fallback to configured days (14)
        assert fake_reader.calls[-1][4] == 14
