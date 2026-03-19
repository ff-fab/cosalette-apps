"""gas2mqtt application entry point.

Wires the cosalette App with all devices, adapters, and settings.
The module-level ``app`` object is the entry point for the CLI:
``gas2mqtt`` runs ``app.run()``.
"""

from __future__ import annotations

import cosalette
from cosalette import OnChange

from gas2mqtt import __version__
from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import magnetometer
from gas2mqtt.devices.temperature import make_pt1, temperature
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings

# --- Settings & store ---
# Eagerly instantiated so registration calls below can use concrete values
# (intervals, enabled flags, state_file). The same class is passed via
# settings_class= so cosalette's DI injects an identical instance into
# device handlers at runtime.

settings = Gas2MqttSettings()

_store: cosalette.Store = (
    cosalette.JsonFileStore(settings.state_file)
    if settings.state_file is not None
    else cosalette.NullStore()
)

# --- App creation ---

app = cosalette.App(
    name="gas2mqtt",
    version=__version__,
    description="Domestic gas meter reader via QMC5883L magnetometer",
    settings_class=Gas2MqttSettings,
    store=_store,
    adapters={
        MagnetometerPort: (Qmc5883lAdapter, FakeMagnetometer),
    },
)
"""Module-level app instance — entry point for the CLI."""

# --- Device registration ---

app.add_device("gas_counter", gas_counter)

app.add_telemetry(
    "temperature",
    temperature,
    interval=settings.temperature_interval,
    publish=OnChange(threshold={"temperature": 0.05}),
    init=make_pt1,
)

app.add_telemetry(
    "magnetometer",
    magnetometer,
    interval=settings.poll_interval,
    enabled=settings.enable_debug_device,
)
