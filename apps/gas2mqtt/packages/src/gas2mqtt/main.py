"""gas2mqtt application entry point.

Wires the cosalette App with all devices, adapters, and lifespan
management.  The module-level ``app`` object is the entry point
for the CLI: ``gas2mqtt`` runs ``app.run()``.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable

import cosalette

from gas2mqtt import __version__
from gas2mqtt.adapters.fake import FakeMagnetometer, NullStorage
from gas2mqtt.adapters.json_storage import JsonFileStorage
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter
from gas2mqtt.devices.gas_counter import gas_counter
from gas2mqtt.devices.magnetometer import make_magnetometer_handler
from gas2mqtt.devices.temperature import make_temperature_handler
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

    Registers the magnetometer adapter (with settings injection),
    storage adapter, gas counter device, temperature telemetry
    (with OnChange publish strategy), and optional debug magnetometer
    telemetry.

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
    # Settings injection (cosalette 0.1.1): the framework resolves
    # Gas2MqttSettings and passes it to the factory automatically.
    def _make_magnetometer(settings: Gas2MqttSettings) -> Qmc5883lAdapter:
        return Qmc5883lAdapter(
            bus_number=settings.i2c_bus, address=settings.i2c_address
        )

    app.adapter(MagnetometerPort, _make_magnetometer, dry_run=FakeMagnetometer)

    # --- Storage adapter registration ---
    def _make_storage() -> JsonFileStorage | NullStorage:
        return _make_storage_adapter(Gas2MqttSettings())

    app.adapter(StateStoragePort, _make_storage, dry_run=NullStorage)

    # --- Device registration ---

    @app.device("gas_counter")
    async def _gas_counter(ctx: cosalette.DeviceContext) -> None:
        await gas_counter(ctx)

    # Registration-time config: read field defaults from the model class.
    _fields = Gas2MqttSettings.model_fields
    temp_interval: float = _fields["temperature_interval"].default
    poll_interval: float = _fields["poll_interval"].default
    enable_debug: bool = _fields["enable_debug_device"].default

    # Temperature: @app.telemetry with OnChange publish strategy.
    # The handler factory returns a closure that captures EWMA filter state,
    # so we lazily initialise it on first call to let cosalette DI provide
    # the adapter and settings.
    _temp_handler: Callable[[], Awaitable[dict[str, object]]] | None = None

    @app.telemetry(
        "temperature",
        interval=temp_interval,
        publish=cosalette.OnChange(threshold={"temperature": 0.05}),
    )
    async def _temperature(
        magnetometer: MagnetometerPort,
        settings: Gas2MqttSettings,
    ) -> dict[str, object]:
        nonlocal _temp_handler
        if _temp_handler is None:
            _temp_handler = make_temperature_handler(magnetometer, settings)
        return await _temp_handler()

    # Magnetometer: conditional @app.telemetry (debug only).
    # Delegates to make_magnetometer_handler() so the tested factory
    # is the same code path used in production.
    if enable_debug:
        _mag_handler: Callable[[], Awaitable[dict[str, object]]] | None = None

        @app.telemetry("magnetometer", interval=poll_interval)
        async def _magnetometer(
            magnetometer: MagnetometerPort,
        ) -> dict[str, object]:
            nonlocal _mag_handler
            if _mag_handler is None:
                _mag_handler = make_magnetometer_handler(magnetometer)
            return await _mag_handler()

    return app


app = create_app()
"""Module-level app instance — entry point for the CLI."""
