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

import asyncio

import pytest

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError, BleReadError
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


class _FailuresThenRecoverReader(FakeAirthingsReader):
    """Exhaust one retryable run, then recover on the next invocation."""

    def __init__(self, failures: int, error: Exception) -> None:
        super().__init__()
        self._failures = failures
        self._error = error

    async def read(self, mac: str) -> AirthingsReading:
        self.calls.append(mac)
        if self._failures:
            self._failures -= 1
            raise self._error
        return self.readings[len(self.calls) % len(self.readings)]


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

        # Act — two poll cycles past startup: first errors, then recovers
        await run_app_briefly(harness, polls=2)

        # Assert — the retry succeeds within the same invocation, so no
        # terminal error is published.
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        assert not harness.messages_for(error_topic)

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

        # Act — two poll cycles past startup: first errors, then recovers
        await run_app_briefly(harness, polls=2)

        # Assert — health status published (app was alive)
        harness.assert_published(f"{TOPIC_PREFIX}/status")

    @pytest.mark.integration
    async def test_retry_exhaustion_marks_offline_then_recovery_online(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """Four retryable failures publish retained offline once, then online."""
        reader = _FailuresThenRecoverReader(
            failures=4, error=BleConnectionError("device unreachable")
        )
        harness = make_harness(adapter=lambda: reader, settings=test_settings)
        availability_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability"
        state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
        task = asyncio.create_task(harness.run())
        try:
            await harness.wait_for_publish_count(availability_topic, 1)
            for _ in range(3):
                await harness.advance_time(10)
            await harness.wait_for_publish_count(availability_topic, 2)
            assert harness.messages_for(availability_topic)[-1] == (
                "offline",
                True,
                1,
            )
            await harness.inject_command(
                DEVICE_NAME, "", topic=f"{TOPIC_PREFIX}/{DEVICE_NAME}/set"
            )
            await harness.wait_for_publish_count(state_topic, 1)
            assert len(reader.calls) == 5
            assert harness.messages_for(availability_topic)[-1] == (
                "online",
                True,
                1,
            )
        finally:
            harness.shutdown_event.set()
            if not task.done():
                await task

        assert (
            harness.messages_for(availability_topic).count(("offline", True, 1)) == 2
        )  # terminal failure + shutdown

    @pytest.mark.integration
    async def test_non_retryable_read_error_publishes_error_but_remains_online(
        self,
        test_settings: Airthings2MqttSettings,
    ) -> None:
        """A data/read failure is reported once without changing availability.

        ``BleReadError`` is deliberately outside the retry policy: it describes
        unusable sensor data, not loss of transport. Cosalette therefore keeps
        the device online; automatic offline is reserved for exhausted retries.
        """
        reader = _FailuresThenRecoverReader(
            failures=1, error=BleReadError("malformed sensor frame")
        )
        harness = make_harness(adapter=lambda: reader, settings=test_settings)

        task = asyncio.create_task(harness.run())
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        availability_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability"
        try:
            await harness.wait_for_publish_count(error_topic, 1)
            assert len(reader.calls) == 1, (
                "BleReadError unexpectedly entered retry policy"
            )
            assert harness.messages_for(availability_topic) == [("online", True, 1)]
        finally:
            harness.shutdown_event.set()
            if not task.done():
                await task


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
        reader = _AlwaysRaisingReader()
        harness = make_harness(adapter=lambda: reader, settings=test_settings)

        # Act — multiple identical-error poll cycles, so dedup is observable
        await run_app_briefly(harness, polls=2)

        # Assert — more than one error was actually raised, so count=1 below
        # proves deduplication rather than passing vacuously on a single run.
        assert len(reader.calls) >= 2, "too few polls — dedup would be vacuous"

        # Assert — error topic should have exactly 1 message (deduplicated)
        error_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/error"
        harness.assert_published(error_topic, count=1)
