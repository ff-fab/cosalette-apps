"""Integration tests for airthings2mqtt full app wiring with AppHarness.

Exercises the real application wiring (startup -> telemetry poll -> MQTT
publish -> shutdown) end-to-end using in-memory test doubles
(FakeAirthingsReader, MockMqttClient), with no real BLE or MQTT I/O.

Test Techniques Used:
- Integration Testing: Full app wiring through cosalette framework
- Specification-based: MQTT topic structure, telemetry payload shape
- State Transition Testing: Startup online -> shutdown offline lifecycle
- Branch Coverage: Scheduled telemetry and on-demand re-read trigger paths
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette import App, MockMqttClient

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.settings import Airthings2MqttSettings

from .conftest import DEVICE_NAME, TOPIC_PREFIX, build_integration_app, run_app_briefly


async def _run_with_trigger(
    test_app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Airthings2MqttSettings,
    *,
    payload: str = "",
    startup_wait: float = 0.3,
    post_trigger_wait: float = 0.2,
) -> None:
    """Start the app, deliver a re-read trigger, then shut down cleanly."""
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        test_app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    await asyncio.sleep(startup_wait)
    await mock_mqtt.deliver(f"{TOPIC_PREFIX}/{DEVICE_NAME}/set", payload)
    await asyncio.sleep(post_trigger_wait)
    shutdown_event.set()
    await task


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
        test_settings: Airthings2MqttSettings,
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
        test_settings: Airthings2MqttSettings,
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
    """Verify that telemetry sensor data is published to the correct topic."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_publishes_sensor_data(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Telemetry handler publishes sensor dict to device state topic.

        Technique: Integration — verify full pipeline from reader to MQTT.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert — telemetry published to device state topic
        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert messages, (
            f"Expected telemetry on {state_topic}; published: {mock_mqtt.published}"
        )

        # Verify payload is valid JSON with expected sensor keys
        payload = json.loads(messages[0][0])
        assert isinstance(payload, dict)
        assert "temperature" in payload
        assert "humidity" in payload
        assert "radon_24h_avg" in payload
        assert "radon_long_term_avg" in payload

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_payload_matches_fake_reader_defaults(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Published values match FakeAirthingsReader default readings.

        Technique: Specification-based — verify wiring from fake adapter to MQTT.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert — values match FakeAirthingsReader defaults
        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert messages, f"Expected telemetry on {state_topic}"

        payload = json.loads(messages[0][0])
        assert payload["temperature"] == 21.5
        assert payload["humidity"] == 45.0
        assert payload["radon_24h_avg"] == 80
        assert payload["radon_long_term_avg"] == 65


class TestTriggeredTelemetry:
    """Verify MQTT /set messages trigger immediate Airthings re-reads."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_empty_set_payload_triggers_reread(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Empty /set payload triggers an extra sensor read and state publish.

        Technique: Integration — verify MQTT inbound trigger reaches telemetry.
        """
        # Arrange
        fake_reader = FakeAirthingsReader()
        test_app = build_integration_app(lambda: fake_reader)

        # Act
        await _run_with_trigger(test_app, mock_mqtt, test_settings)

        # Assert — one startup read plus one triggered re-read
        assert fake_reader.calls.count(test_settings.device_mac) >= 2

        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        messages = mock_mqtt.get_messages_for(state_topic)
        assert len(messages) >= 2, (
            f"Expected at least 2 state publishes (startup + trigger); "
            f"got {len(messages)} on {state_topic}"
        )


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
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Device availability published as 'online' on startup.

        Technique: Specification-based — verify cosalette availability wiring.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert — check availability topic for online message
        avail_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability"
        messages = mock_mqtt.get_messages_for(avail_topic)
        assert messages, (
            f"Expected availability on {avail_topic}; "
            f"published topics: {[t for t, *_ in mock_mqtt.published]}"
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
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Device availability published as 'offline' on graceful shutdown.

        Technique: State Transition — verify offline published on shutdown.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert — check availability topic for offline message
        avail_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability"
        messages = mock_mqtt.get_messages_for(avail_topic)
        assert messages, f"Expected availability on {avail_topic}"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("offline" in p for p in payloads), (
            f"No 'offline' availability found; got: {payloads}"
        )
