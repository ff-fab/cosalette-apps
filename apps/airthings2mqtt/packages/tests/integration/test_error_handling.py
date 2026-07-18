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

import pytest

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError
from airthings2mqtt.ports import AirthingsReading
from airthings2mqtt.settings import Airthings2MqttSettings

from .conftest import (
    DEVICE_NAME,
    TOPIC_PREFIX,
    make_harness,
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
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """BleConnectionError is published to per-device error topic.

        Technique: Error Guessing — verify error routing through full stack.
        """
        # Arrange
        harness = make_harness(adapter=_AlwaysRaisingReader, settings=test_settings)

        # Act
        await run_app_briefly(harness)

        # Assert — per-device error topic has messages
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        harness.assert_published(error_topic)

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_ble_error_published_to_global_error_topic(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """BleConnectionError is also published to the global error topic.

        Technique: Specification-based — global error topic contract.
        """
        # Arrange
        harness = make_harness(adapter=_AlwaysRaisingReader, settings=test_settings)

        # Act
        await run_app_briefly(harness)

        # Assert — global error topic has messages
        harness.assert_published(f"{TOPIC_PREFIX}/error")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_error_payload_is_valid_json_with_message(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Error payload is valid JSON containing the error message.

        Technique: Specification-based — error payload structure.
        """
        # Arrange
        harness = make_harness(adapter=_AlwaysRaisingReader, settings=test_settings)

        # Act
        await run_app_briefly(harness)

        # Assert — error payload contains the error message
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        harness.assert_published(error_topic, contains="device unreachable")


# ---------------------------------------------------------------------------
# Recovery after error
# ---------------------------------------------------------------------------


class TestErrorRecovery:
    """Verify that the app recovers after a transient BLE error."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_recovery_publishes_valid_telemetry_after_error(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """After first-call error, second poll publishes valid sensor state.

        Technique: State Transition — error -> recovery -> telemetry published.
        """
        # Arrange
        harness = make_harness(adapter=_ErrorThenRecoverReader, settings=test_settings)

        # Act — wait long enough for at least 2 poll cycles (interval=1s)
        await run_app_briefly(harness, wait=1.5)

        # Assert — error was published
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        harness.assert_published(error_topic)

        # Assert — valid telemetry was also published (recovery) with sensor keys
        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        harness.assert_published(state_topic, contains="temperature")
        harness.assert_published(state_topic, contains="humidity")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_app_stays_alive_through_error_and_recovery(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """App publishes health status even after experiencing an error.

        Technique: State Transition — app does not crash on transient error.
        """
        # Arrange
        harness = make_harness(adapter=_ErrorThenRecoverReader, settings=test_settings)

        # Act — wait long enough for at least 2 poll cycles (interval=1s)
        await run_app_briefly(harness, wait=1.5)

        # Assert — health status published (app was alive)
        harness.assert_published(f"{TOPIC_PREFIX}/status")


# ---------------------------------------------------------------------------
# Error deduplication
# ---------------------------------------------------------------------------


class TestErrorDeduplication:
    """Verify cosalette deduplicates consecutive identical errors."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_consecutive_identical_errors_are_deduplicated(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Consecutive identical BleConnectionErrors publish only one error message.

        Technique: Specification-based — cosalette error deduplication contract.
        Consecutive identical errors are logged once; the error topic should
        not be flooded with duplicates.
        """
        # Arrange
        harness = make_harness(adapter=_AlwaysRaisingReader, settings=test_settings)

        # Act — run long enough for multiple poll cycles (>= 2 intervals)
        await run_app_briefly(harness, wait=2.5)

        # Assert — error topic should have exactly 1 message (deduplicated)
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        harness.assert_published(error_topic, count=1)
