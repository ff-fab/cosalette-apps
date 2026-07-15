"""Integration test fixtures for gas2mqtt.

Provides a fully-wired App helper for integration tests that drive the
real application logic without real hardware or MQTT I/O.
"""

from __future__ import annotations

import asyncio

from cosalette import App, MockMqttClient

from gas2mqtt.settings import Gas2MqttSettings


async def run_app_briefly(
    test_app: App,
    mock_mqtt: MockMqttClient,
    test_settings: Gas2MqttSettings,
    *,
    wait: float = 0.5,
) -> None:
    """Start the app as a background task, wait, then shut it down cleanly.

    Guarantees shutdown_event is set even on cancellation, and bounds task
    completion with asyncio.wait_for to prevent indefinite test hangs.
    """
    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        test_app._run_async(
            mqtt=mock_mqtt,
            settings=test_settings,
            shutdown_event=shutdown_event,
        )
    )
    try:
        await asyncio.sleep(wait)
    finally:
        shutdown_event.set()
    await asyncio.wait_for(task, timeout=wait * 5)
