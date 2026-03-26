"""Integration tests for error handling and recovery.

Verifies that BLE read failures are published as MQTT error messages,
that the application recovers on the next successful poll, and that
consecutive identical errors are deduplicated by cosalette.

Test Techniques Used:
- Error Guessing: BleConnectionError during telemetry poll
- State Transition: error -> recovery -> valid telemetry published
- Specification-based: error topic structure, error deduplication
"""

from __future__ import annotations

import json

import pytest
from cosalette import MockMqttClient

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError
from airthings2mqtt.ports import AirthingsReading
from airthings2mqtt.settings import Airthings2MqttSettings

from .conftest import (
    DEVICE_NAME,
    TOPIC_PREFIX,
    build_integration_app,
    run_app_briefly,
)

# ---------------------------------------------------------------------------
# Test adapter subclasses
# ---------------------------------------------------------------------------


class _ErrorThenRecoverReader(FakeAirthingsReader):
    """Raises BleConnectionError on the first read, then returns valid data.

    Used to test the error -> recovery transition path.
    """

    def __init__(self) -> None:
        super().__init__()
        self._first_call = True

    async def read(self, mac: str) -> AirthingsReading:
        """Raise on first call, delegate to parent on subsequent calls."""
        if self._first_call:
            self.calls.append(mac)
            self._first_call = False
            raise BleConnectionError("device unreachable")
        return await super().read(mac)


class _AlwaysRaisingReader(FakeAirthingsReader):
    """Raises BleConnectionError on every read.

    Used to test error deduplication — consecutive identical errors
    should be logged only once by cosalette.
    """

    async def read(self, mac: str) -> AirthingsReading:
        """Always raise BleConnectionError."""
        self.calls.append(mac)
        raise BleConnectionError("device unreachable")


# ---------------------------------------------------------------------------
# Error publishing
# ---------------------------------------------------------------------------


class TestErrorPublishing:
    """Verify that BLE errors are published to the correct MQTT error topics."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_ble_error_published_to_device_error_topic(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """BleConnectionError is published to per-device error topic.

        Technique: Error Guessing — verify error routing through full stack.
        """
        # Arrange
        app = build_integration_app(adapter=_AlwaysRaisingReader)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert — per-device error topic has messages
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages, (
            f"Expected error on {error_topic}; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_ble_error_published_to_global_error_topic(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """BleConnectionError is also published to the global error topic.

        Technique: Specification-based — global error topic contract.
        """
        # Arrange
        app = build_integration_app(adapter=_AlwaysRaisingReader)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert — global error topic has messages
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/error")
        assert messages, (
            f"Expected error on {TOPIC_PREFIX}/error; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_error_payload_is_valid_json_with_message(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Error payload is valid JSON containing the error message.

        Technique: Specification-based — error payload structure.
        """
        # Arrange
        app = build_integration_app(adapter=_AlwaysRaisingReader)

        # Act
        await run_app_briefly(app, mock_mqtt, test_settings)

        # Assert — parse error payload
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages
        payload = json.loads(messages[0][0])
        assert "message" in payload
        assert "device unreachable" in payload["message"]


# ---------------------------------------------------------------------------
# Recovery after error
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    """Verify that the app recovers after a transient BLE error."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_recovery_publishes_valid_telemetry_after_error(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """After first-call error, second poll publishes valid sensor state.

        Technique: State Transition — error -> recovery -> telemetry published.
        """
        # Arrange
        app = build_integration_app(adapter=_ErrorThenRecoverReader)

        # Act — wait long enough for at least 2 poll cycles (interval=1s)
        await run_app_briefly(app, mock_mqtt, test_settings, wait=1.5)

        # Assert — error was published
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        error_msgs = mock_mqtt.get_messages_for(error_topic)
        assert error_msgs, f"Expected error on {error_topic}"

        # Assert — valid telemetry was also published (recovery)
        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        state_msgs = mock_mqtt.get_messages_for(state_topic)
        assert state_msgs, (
            f"Expected recovery telemetry on {state_topic} after transient error; "
            f"published topics: {sorted({t for t, *_ in mock_mqtt.published})}"
        )

        # Assert — payload has expected sensor keys
        payload = json.loads(state_msgs[0][0])
        assert "temperature" in payload
        assert "humidity" in payload

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_app_stays_alive_through_error_and_recovery(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """App publishes health status even after experiencing an error.

        Technique: State Transition — app does not crash on transient error.
        """
        # Arrange
        app = build_integration_app(adapter=_ErrorThenRecoverReader)

        # Act — wait long enough for at least 2 poll cycles (interval=1s)
        await run_app_briefly(app, mock_mqtt, test_settings, wait=1.5)

        # Assert — health status published (app was alive)
        status_msgs = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        assert status_msgs, "Expected health status after error and recovery"


# ---------------------------------------------------------------------------
# Error deduplication
# ---------------------------------------------------------------------------


class TestErrorDeduplication:
    """Verify cosalette deduplicates consecutive identical errors."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_consecutive_identical_errors_are_deduplicated(
        self,
        mock_mqtt: MockMqttClient,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Consecutive identical BleConnectionErrors publish only one error message.

        Technique: Specification-based — cosalette error deduplication contract.
        Consecutive identical errors are logged once; the error topic should
        not be flooded with duplicates.
        """
        # Arrange
        app = build_integration_app(adapter=_AlwaysRaisingReader)

        # Act — run long enough for multiple poll cycles (>= 2 intervals)
        await run_app_briefly(app, mock_mqtt, test_settings, wait=2.5)

        # Assert — error topic should have exactly 1 message (deduplicated)
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        messages = mock_mqtt.get_messages_for(error_topic)
        assert messages, f"Expected at least one error on {error_topic}"
        assert len(messages) == 1, (
            f"Expected exactly 1 deduplicated error message, got {len(messages)}; "
            "cosalette should suppress consecutive identical errors"
        )
