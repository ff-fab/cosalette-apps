"""gas2mqtt application entry point."""

from __future__ import annotations

import cosalette
from cosalette import OnChange, SaveOnChange

from gas2mqtt import __version__
from gas2mqtt._store_path import resolve_store_path
from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter, make_gas_counter
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import make_pt1, temperature
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings


def _make_store() -> cosalette.Store:
    return cosalette.JsonFileStore(resolve_store_path())


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

app.telemetry(
    "gas_counter",
    interval=lambda s: s.poll_interval,
    triggerable=True,
    publish=OnChange(),
    persist=SaveOnChange(),
    init=make_gas_counter,
)(gas_counter)

app.telemetry(
    "temperature",
    interval=lambda s: s.temperature_interval,
    publish=OnChange(threshold={"temperature": 0.05}),
    init=make_pt1,
)(temperature)

app.telemetry(
    "magnetometer",
    interval=lambda s: s.poll_interval,
    enabled=lambda s: s.enable_debug_device,
)(magnetometer)

cli = app.cli
