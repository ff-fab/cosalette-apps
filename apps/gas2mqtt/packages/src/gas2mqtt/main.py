"""gas2mqtt application entry point.

Wires the cosalette App with all devices, adapters, and lifespan
management.  The module-level ``app`` object is the entry point
for the CLI: ``gas2mqtt`` runs ``app.run()``.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import cosalette

from gas2mqtt import __version__
from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import magnetometer_device
from gas2mqtt.devices.temperature import temperature_device
from gas2mqtt.ports import MagnetometerPort
from gas2mqtt.settings import Gas2MqttSettings


@contextlib.asynccontextmanager
async def lifespan(ctx: cosalette.AppContext) -> AsyncIterator[None]:
    """Initialize and clean up the magnetometer I2C connection.

    Opens the I2C bus and configures the QMC5883L registers on startup.
    Closes the bus on shutdown.  For dry-run mode and tests, the
    FakeMagnetometer's ``initialize()``/``close()`` are harmless no-ops.
    """
    magnetometer = ctx.adapter(MagnetometerPort)  # type: ignore[type-abstract]
    magnetometer.initialize()
    try:
        yield
    finally:
        magnetometer.close()


def create_app() -> cosalette.App:
    """Create and wire the gas2mqtt application.

    Registers the magnetometer adapter, gas counter device,
    temperature device, and optional debug magnetometer device.

    Returns:
        Fully configured cosalette App ready to run.
    """
    app = cosalette.App(
        name="gas2mqtt",
        version=__version__,
        description="Domestic gas meter reader via QMC5883L magnetometer",
        settings_class=Gas2MqttSettings,
        lifespan=lifespan,
    )

    # --- Adapter registration ---
    # Factory callable: cosalette invokes this after parsing settings.
    # A lightweight Gas2MqttSettings() reads the same env/.env values
    # that the framework already parsed, ensuring the adapter receives
    # the user-configured I2C bus and address.
    def _make_magnetometer() -> Qmc5883lAdapter:
        s = Gas2MqttSettings()
        return Qmc5883lAdapter(bus_number=s.i2c_bus, address=s.i2c_address)

    app.adapter(MagnetometerPort, _make_magnetometer, dry_run=FakeMagnetometer)

    # --- Device registration ---

    @app.device("gas_counter")
    async def _gas_counter(ctx: cosalette.DeviceContext) -> None:
        await gas_counter(ctx)

    @app.device("temperature")
    async def _temperature(ctx: cosalette.DeviceContext) -> None:
        await temperature_device(ctx)

    @app.device("magnetometer")
    async def _magnetometer(ctx: cosalette.DeviceContext) -> None:
        await magnetometer_device(ctx)

    return app


app = create_app()
"""Module-level app instance — entry point for the CLI."""
