"""Integration test fixtures for gas2mqtt.

Provides a fully-wired App helper for integration tests that drive the
real application logic without real hardware or MQTT I/O.
"""

from __future__ import annotations

import asyncio
import logging

from cosalette import (
    App,
    DeviceStore,
    FixedBackoff,
    MemoryStore,
    MockMqttClient,
    OnChange,
    setting_ref,
)

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.gas_counter import (
    GasCounterReading,
    GasCounterState,
    gas_counter,
    make_gas_counter,
    update_consumption,
)
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import TemperatureReading, make_pt1, temperature
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings


def build_full_integration_app() -> App:
    """Construct a fully-wired App mirroring gas2mqtt.main.create_app().

    Substitutes ``FakeMagnetometer`` for the real QMC5883L adapter and
    ``MemoryStore`` for the JsonFileStore, so tests exercise the real
    handler registrations (gas_counter, consumption, temperature,
    magnetometer) without hardware or filesystem I/O.
    """
    app = App(
        name="gas2mqtt",
        version="0.0.0",
        settings_class=Gas2MqttSettings,
        store=MemoryStore(),
        adapters={MagnetometerPort: FakeMagnetometer},
    )

    @app.state
    def gas_counter_state(settings: Gas2MqttSettings) -> GasCounterState:
        store = MemoryStore()
        device_store = DeviceStore(store, "gas_counter")
        return make_gas_counter(settings, device_store, logging.getLogger(__name__))

    app.telemetry(
        "gas_counter",
        interval=setting_ref("poll_interval"),
        publish=OnChange(),
        retry=3,
        retry_on=(OSError,),
        backoff=FixedBackoff(delay=0.05),
        state_model=GasCounterReading,
    )(gas_counter)

    app.command(
        "consumption",
        payload_model=dict,
    )(update_consumption)

    app.telemetry(
        "temperature",
        interval=setting_ref("temperature_interval"),
        publish=OnChange(threshold={"temperature": 0.05}),
        retry=3,
        retry_on=(OSError,),
        init=make_pt1,
        state_model=TemperatureReading,
    )(temperature)

    app.telemetry(
        "magnetometer",
        interval=setting_ref("poll_interval"),
        retry=3,
        retry_on=(OSError,),
        backoff=FixedBackoff(delay=0.05),
        enabled=lambda s: s.enable_debug_device,
    )(magnetometer)

    return app


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
