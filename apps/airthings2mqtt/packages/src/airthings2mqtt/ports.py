"""Hardware adapter ports for airthings2mqtt.

Defines Protocol classes for hardware interfaces, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code
depends only on these protocols — concrete adapters are injected
at runtime by cosalette's adapter registry.

Consumer-metadata maintenance (model-driven)
--------------------------------------------
:class:`AirthingsReading` is the ``state_model`` for the ``airthings``
telemetry channel (see :mod:`airthings2mqtt.main`), so ``cosalette schema
init`` emits typed payload properties carrying ``x-cosalette-consumer``
metadata (device_class, unit, state_class, icon, …) for Home Assistant MQTT
discovery. The metadata rides on each field via :func:`pydantic.Field`'s
``json_schema_extra`` (built through the framework
:func:`cosalette.schema.consumer` helper). Because cosalette generates the
schema with ``TypeAdapter(model).json_schema()``, which preserves
``json_schema_extra``, this enrichment *survives*
``task airthings2mqtt:schema:generate`` — no post-generation hand-application.
Mirrors velux2mqtt's ``CoverState`` and gas2mqtt's telemetry payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Protocol, runtime_checkable

from cosalette import HealthCheckable
from cosalette.schema import consumer
from pydantic import Field


def _radon(display_name: str) -> dict[str, Any]:
    """``x-cosalette-consumer`` for a radon-level sensor (Bq/m³).

    Collapses the ``unit="Bq/m³"``, ``state_class="measurement"``,
    ``icon="mdi:radioactive"`` triple shared by the 24h and long-term radon
    fields, where only the ``display_name`` varies.
    """
    return consumer(
        display_name=display_name,
        unit="Bq/m³",
        state_class="measurement",
        icon="mdi:radioactive",
    )


@dataclass(frozen=True, slots=True)
class AirthingsReading:
    """A single reading from an Airthings Wave sensor.

    Attributes:
        temperature: Temperature in degrees Celsius.
        humidity: Relative humidity as a percentage.
        radon_24h_avg: 24-hour average radon level in Bq/m³.
        radon_long_term_avg: Long-term average radon level in Bq/m³.
    """

    temperature: Annotated[
        float,
        Field(
            json_schema_extra=consumer(
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    humidity: Annotated[
        float,
        Field(
            json_schema_extra=consumer(
                device_class="humidity",
                unit="%",
                state_class="measurement",
            )
        ),
    ]
    radon_24h_avg: Annotated[int, Field(json_schema_extra=_radon("Radon (24h avg)"))]
    radon_long_term_avg: Annotated[
        int, Field(json_schema_extra=_radon("Radon (long-term avg)"))
    ]


@runtime_checkable
class AirthingsReaderPort(HealthCheckable, Protocol):
    """Port for reading Airthings Wave BLE sensor data.

    Implementations must connect to the BLE device, read the four
    GATT characteristics (temperature, humidity, radon 24h, radon
    long-term), and return an AirthingsReading.
    """

    async def read(self, mac: str) -> AirthingsReading:
        """Read sensor data from the Airthings Wave device.

        Connects to the device, reads all four characteristics,
        disconnects, and returns the parsed reading.

        Args:
            mac: Bluetooth MAC address of the Airthings Wave device.

        Returns:
            AirthingsReading with temperature, humidity, and radon values.

        Raises:
            BleConnectionError: If the device cannot be reached.
            BleReadError: If a GATT characteristic cannot be read.
            BleTimeoutError: If the connection or read times out.
        """
        ...
