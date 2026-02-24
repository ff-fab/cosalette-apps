"""gas2mqtt application entry point.

Wires the cosalette App with all devices, adapters, and lifespan
management.  The module-level ``app`` object is the entry point
for the CLI: ``gas2mqtt`` runs ``app.run()``.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import cosalette
from cosalette import OnChange, Pt1Filter

from gas2mqtt import __version__
from gas2mqtt.adapters.fake import FakeMagnetometer, NullStorage
from gas2mqtt.adapters.json_storage import JsonFileStorage
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.ports import MagnetometerPort, StateStoragePort
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


def _make_storage_adapter(
    settings: Gas2MqttSettings,
) -> JsonFileStorage | NullStorage:
    """Create the appropriate storage adapter based on settings.

    Returns :class:`NullStorage` when ``state_file`` is ``None``
    (persistence disabled), otherwise :class:`JsonFileStorage`
    pointing at the configured path.
    """
    if settings.state_file is None:
        return NullStorage()
    return JsonFileStorage(settings.state_file)


def create_app() -> cosalette.App:
    """Create and wire the gas2mqtt application.

    Registers adapters, the gas counter device, temperature telemetry
    (with PT1 smoothing and OnChange publish strategy), and optional
    debug magnetometer telemetry.

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

    # Eager settings (cosalette 0.1.4) — available at registration time.
    settings: Gas2MqttSettings = app.settings  # type: ignore[assignment]

    # --- Adapter registration ---

    def _make_magnetometer(settings: Gas2MqttSettings) -> Qmc5883lAdapter:
        return Qmc5883lAdapter(
            bus_number=settings.i2c_bus, address=settings.i2c_address
        )

    app.adapter(MagnetometerPort, _make_magnetometer, dry_run=FakeMagnetometer)

    app.adapter(StateStoragePort, _make_storage_adapter, dry_run=NullStorage)

    # --- Device registration ---

    @app.device("gas_counter")
    async def _gas_counter(ctx: cosalette.DeviceContext) -> None:
        await gas_counter(ctx)

    # Temperature: PT1 filter initialised via init= callback.
    # cosalette DI provides settings to the init function automatically.
    def _make_pt1(settings: Gas2MqttSettings) -> Pt1Filter:
        return Pt1Filter(tau=settings.smoothing_tau, dt=settings.temperature_interval)

    @app.telemetry(
        "temperature",
        interval=settings.temperature_interval,
        publish=OnChange(threshold={"temperature": 0.05}),
        init=_make_pt1,
    )
    async def _temperature(
        magnetometer: MagnetometerPort,
        settings: Gas2MqttSettings,
        pt1: Pt1Filter,
    ) -> dict[str, object]:
        reading = magnetometer.read()
        raw_celsius = (
            settings.temp_scale * reading.temperature_raw + settings.temp_offset
        )
        return {"temperature": round(pt1.update(raw_celsius), 1)}

    # Magnetometer: conditional telemetry (debug only).
    if settings.enable_debug_device:

        @app.telemetry("magnetometer", interval=settings.poll_interval)
        async def _magnetometer(
            magnetometer: MagnetometerPort,
        ) -> dict[str, object]:
            reading = magnetometer.read()
            return {"bx": reading.bx, "by": reading.by, "bz": reading.bz}

    return app


app = create_app()
"""Module-level app instance — entry point for the CLI."""
