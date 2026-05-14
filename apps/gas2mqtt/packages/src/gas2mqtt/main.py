"""gas2mqtt application entry point."""

from __future__ import annotations

import logging

import cosalette
from cosalette import DeviceStore, OnChange, setting_ref

from gas2mqtt import __version__
from gas2mqtt._store_path import resolve_store_path
from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import (
    GasCounterState,
    gas_counter,
    make_gas_counter,
    update_consumption,
)
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import make_pt1, temperature
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings


def _make_store(settings: Gas2MqttSettings) -> cosalette.Store:
    store_path = settings.state_file or resolve_store_path()
    return cosalette.JsonFileStore(store_path)


def create_app() -> cosalette.App:
    app = cosalette.App(
        name="gas2mqtt",
        version=__version__,
        description="Domestic gas meter reader via QMC5883L magnetometer",
        settings_class=Gas2MqttSettings,
        store=_make_store,
        adapters={
            MagnetometerPort: (Qmc5883lAdapter, FakeMagnetometer),
        },
    )

    @app.state
    def gas_counter_state(settings: Gas2MqttSettings) -> GasCounterState:
        """State provider for shared GasCounterState.

        Both gas_counter telemetry and update_consumption command receive
        the same GasCounterState instance via DI, ensuring consistent
        in-process state. Explicit save() in stage_state() handles persistence.
        """
        logger = logging.getLogger("gas2mqtt.state")
        store_backend = _make_store(settings)
        device_store = DeviceStore(store_backend, "gas_counter")
        return make_gas_counter(settings, device_store, logger)

    app.telemetry(
        "gas_counter",
        interval=setting_ref("poll_interval"),
        publish=OnChange(),
        # No persist=SaveOnChange() — stage_state() calls store.save() directly
        # No init=make_gas_counter — GasCounterState injected from @app.state
        summary="Domestic gas meter counter: pulse counting via QMC5883L Schmitt trigger detection",
        state_model=GasCounterState,
        behavior=[
            "Read 3-axis magnetic field from QMC5883L via MagnetometerPort",
            "Feed Bz value through SchmittTrigger for hysteresis-based edge detection",
            "Increment counter on rising edge (LOW→HIGH transition)",
            "Optionally increment ConsumptionTracker by liters_per_tick/1000 m³",
            "Stage updated counter and consumption_m3 to DeviceStore with explicit save",
        ],
        effects=[
            "Publishes counter, trigger state, and optionally consumption_m3 to MQTT",
            "Persists counter and consumption_m3 to JsonFileStore on every state change",
        ],
    )(gas_counter)

    app.command(
        "consumption",
        # No init= — GasCounterState injected from @app.state (same instance as telemetry)
        summary="Override the accumulated consumption_m3 value for the gas counter",
        payload_model=dict,
        effects=[
            "Updates consumption_m3 in the shared GasCounterState",
            "Persists new consumption_m3 to JsonFileStore immediately",
            "Publishes updated gas counter state to MQTT",
        ],
    )(update_consumption)

    app.telemetry(
        "temperature",
        interval=setting_ref("temperature_interval"),
        publish=OnChange(threshold={"temperature": 0.05}),
        init=make_pt1,
    )(temperature)

    app.telemetry(
        "magnetometer",
        interval=setting_ref("poll_interval"),
        enabled=lambda s: s.enable_debug_device,
    )(magnetometer)

    return app


app = create_app()

cli = app.cli
