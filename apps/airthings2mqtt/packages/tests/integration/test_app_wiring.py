"""Integration tests for airthings2mqtt full app wiring with AppHarness.

Exercises the real application wiring (startup -> telemetry poll -> MQTT
publish -> shutdown) end-to-end using in-memory test doubles
(FakeAirthingsReader, MockMqttClient), with no real BLE or MQTT I/O.

Test Techniques Used:
- Integration Testing: Full app wiring through cosalette framework
- Specification-based: MQTT topic structure, telemetry payload shape
- State Transition Testing: Startup online -> shutdown offline lifecycle
- Branch Coverage: Scheduled telemetry and on-demand re-read trigger paths
- Boundary Value Analysis: Deterministic publish-count polling replaces fixed sleeps
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, FakeClock

from airthings2mqtt.adapters.fake import FakeAirthingsReader

from .conftest import (
    DEVICE_NAME,
    TOPIC_PREFIX,
    build_integration_app,
    make_long_poll_settings,
    run_app_briefly,
)


async def _wait_for_publish_count(
    harness: AppHarness,
    topic: str,
    count: int,
    timeout: float = 2.0,
) -> None:
    """Poll until ``topic`` has at least ``count`` messages.

    Uses ``asyncio.wait_for`` with bounded polling so the test fails fast
    rather than hanging indefinitely when the expected publish never arrives.
    """

    async def _poll() -> None:
        while len(harness.mqtt.get_messages_for(topic)) < count:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_poll(), timeout=timeout)


async def _run_with_trigger(
    harness: AppHarness,
    *,
    payload: str = "",
) -> None:
    """Start the app, deliver a re-read trigger, then shut down cleanly.

    Uses deterministic synchronization: waits for the initial startup poll to
    publish to the state topic before delivering the trigger, then waits for
    the triggered re-read publish before shutting down.

    A try/finally ensures shutdown_event is set and the app task is cancelled
    if any wait times out, so stray tasks never leak into subsequent tests.
    """
    state_topic = f"{TOPIC_PREFIX}/{DEVICE_NAME}/state"
    task = asyncio.create_task(harness.run())
    try:
        await _wait_for_publish_count(harness, state_topic, count=1)
        await harness.inject_command(
            DEVICE_NAME, payload, topic=f"{TOPIC_PREFIX}/{DEVICE_NAME}/set"
        )
        await _wait_for_publish_count(harness, state_topic, count=2)
        harness.shutdown_event.set()
        await task
    finally:
        harness.shutdown_event.set()  # idempotent — safe to call twice
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


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
    """Verify that telemetry sensor data is published to the correct topic."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_publishes_sensor_data(
        self,
        harness: AppHarness,
    ) -> None:
        """Telemetry handler publishes sensor dict to device state topic.

        Technique: Integration — verify full pipeline from reader to MQTT.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — telemetry published to device state topic with sensor keys
        harness.assert_state(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/state",
            {
                "temperature": 21.5,
                "humidity": 45.0,
                "radon_24h_avg": 80,
                "radon_long_term_avg": 65,
            },
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_telemetry_payload_matches_fake_reader_defaults(
        self,
        harness: AppHarness,
    ) -> None:
        """Published values match FakeAirthingsReader default readings.

        Technique: Specification-based — verify wiring from fake adapter to MQTT.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — values match FakeAirthingsReader defaults
        harness.assert_state(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/state",
            {
                "temperature": 21.5,
                "humidity": 45.0,
                "radon_24h_avg": 80,
                "radon_long_term_avg": 65,
            },
        )


class TestTriggeredTelemetry:
    """Verify MQTT /set messages trigger immediate Airthings re-reads."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_empty_set_payload_triggers_reread(self) -> None:
        """Empty /set payload triggers an extra sensor read and state publish.

        Uses a 1-hour poll interval so the second state publish cannot be a
        scheduled tick — it must be the triggered re-read.

        Technique: Integration — verify MQTT inbound trigger reaches telemetry.
        """
        # Arrange
        fake_reader = FakeAirthingsReader()
        long_poll = make_long_poll_settings()
        trigger_harness = AppHarness(
            app=build_integration_app(lambda: fake_reader),
            mqtt=MockMqttClient(),
            clock=FakeClock(),
            settings=long_poll,
            shutdown_event=asyncio.Event(),
        )

        # Act
        await _run_with_trigger(trigger_harness)

        # Assert — one startup read plus one triggered re-read
        assert fake_reader.calls.count(long_poll.device_mac) >= 2
        trigger_harness.assert_state(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/state",
            {
                "temperature": 21.5,
                "humidity": 45.0,
                "radon_24h_avg": 80,
                "radon_long_term_avg": 65,
            },
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
        harness: AppHarness,
    ) -> None:
        """Device availability published as 'online' on startup.

        Technique: Specification-based — verify cosalette availability wiring.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — check availability topic for online message
        harness.assert_published(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability", contains="online"
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

        # Assert — check availability topic for offline message
        harness.assert_published(
            f"{TOPIC_PREFIX}/{DEVICE_NAME}/availability", contains="offline"
        )
