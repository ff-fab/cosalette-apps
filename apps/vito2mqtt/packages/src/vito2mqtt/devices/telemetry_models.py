# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Typed ``state_model`` payloads for every telemetry signal group.

Each frozen dataclass mirrors the serialized dict returned by the
corresponding telemetry handler (see :mod:`vito2mqtt.devices.telemetry`).
Wiring these as ``state_model=`` on ``app.add_telemetry`` makes
``cosalette schema init`` emit *typed* payload properties instead of a
bare ``type: object``.  Typed properties can then carry
``x-cosalette-consumer`` metadata that drives Home Assistant MQTT
discovery (device_class, unit, state_class, …).

Design notes
------------
- ``state_model`` is schema-only: cosalette does **not** validate runtime
  payloads against it, so handlers keep returning plain ``dict`` values.
  The dataclasses exist purely to shape the generated AsyncAPI schema.
- Field types match the *serialized* form (post
  :func:`~vito2mqtt.devices._serialization.serialize_value`), not the raw
  codec types.  Notably ``ReturnStatus`` signals serialize to ``str`` and
  ES (error-history) signals serialize to :class:`ErrorHistoryEntry`.
- :data:`GROUP_STATE_MODELS` maps each signal-group key to its model so the
  registration loop can look models up by group name.

Consumer-metadata maintenance (model-driven)
--------------------------------------------
The ``x-cosalette-consumer`` metadata that drives HA discovery
(device_class, unit, state_class, icon, …) rides on each surfaced field
via :func:`pydantic.Field`'s ``json_schema_extra`` (built through the
:func:`_consumer` helper). Because cosalette generates the schema with
``TypeAdapter(model).json_schema()``, which preserves ``json_schema_extra``,
this enrichment *survives* ``task vito2mqtt:schema:generate`` — no
post-generation hand-application step. This mirrors velux2mqtt's
``CoverState``. The migration away from hand-authored ``docs/schema.yaml``
enrichment is tracked as bead ``cap-g90``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import Field

__all__ = [
    "ErrorHistoryEntry",
    "OutdoorState",
    "HotWaterState",
    "BurnerState",
    "HeatingRadiatorState",
    "HeatingFloorState",
    "SystemState",
    "DiagnosisState",
    "GROUP_STATE_MODELS",
]


def _consumer(**metadata: object) -> dict[str, Any]:
    """Wrap HA-discovery metadata under the ``x-cosalette-consumer`` key.

    Returned dict is passed as ``json_schema_extra`` to
    :func:`pydantic.Field`, so ``TypeAdapter(model).json_schema()`` emits the
    ``x-cosalette-consumer`` block that drives Home Assistant MQTT discovery.
    Surviving schema regeneration is the whole point — see the module
    docstring.
    """

    return {"x-cosalette-consumer": metadata}


@dataclass(frozen=True, slots=True)
class ErrorHistoryEntry:
    """A single decoded error-history slot (ES codec type).

    Attributes:
        error: Human-readable error label (localized by ``signal_language``).
        timestamp: ISO 8601 timestamp of the logged event.
    """

    error: str
    timestamp: str


@dataclass(frozen=True, slots=True)
class OutdoorState:
    """Outdoor temperature sensor group payload (°C)."""

    outdoor_temperature: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Outdoor Temperature",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    outdoor_temperature_lowpass: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Outdoor Temperature (Low-pass)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    outdoor_temperature_damped: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Outdoor Temperature (Damped)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]


@dataclass(frozen=True, slots=True)
class HotWaterState:
    """Domestic hot water temperature group payload (°C)."""

    hot_water_temperature: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Hot Water Temperature",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    hot_water_outlet_temperature: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Hot Water Outlet Temperature",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]


@dataclass(frozen=True, slots=True)
class BurnerState:
    """Burner temperatures, modulation, and runtime counters."""

    boiler_temperature: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Boiler Temperature",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    boiler_temperature_lowpass: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Boiler Temperature (Low-pass)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    boiler_temperature_setpoint: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Boiler Temperature Setpoint",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    exhaust_temperature: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Exhaust Temperature",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    burner_modulation: Annotated[
        int,
        Field(
            json_schema_extra=_consumer(
                display_name="Burner Modulation",
                unit="%",
                state_class="measurement",
                icon="mdi:fire",
            )
        ),
    ]
    burner_starts: Annotated[
        int,
        Field(
            json_schema_extra=_consumer(
                display_name="Burner Starts",
                state_class="total_increasing",
                icon="mdi:fire",
            )
        ),
    ]
    burner_hours_stage1: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Burner Hours (Stage 1)",
                device_class="duration",
                unit="h",
                state_class="total_increasing",
                icon="mdi:timer-outline",
            )
        ),
    ]
    plant_power_output: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Plant Power Output",
                unit="%",
                state_class="measurement",
                icon="mdi:gauge",
            )
        ),
    ]


@dataclass(frozen=True, slots=True)
class HeatingRadiatorState:
    """Radiator heating circuit (M1) temperatures, pump, and modes.

    Note:
        ``pump_status_m1`` is an integer status code on this circuit, unlike
        the floor circuit's ``ReturnStatus`` string — the two circuits use
        different codec types.
    """

    flow_temperature_m1: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Flow Temperature M1 (Radiator)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    flow_temperature_setpoint_m1: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Flow Temperature Setpoint M1 (Radiator)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    pump_status_m1: (
        int  # int status code — M1 uses a different codec than M2's ReturnStatus str
    )
    frost_warning_m1: int
    frost_limit_m1: int
    operating_mode_m1: str
    operating_mode_economy_m1: str


@dataclass(frozen=True, slots=True)
class HeatingFloorState:
    """Floor heating circuit (M2) temperatures, pump, and modes.

    Note:
        ``pump_status_m2`` is a ``ReturnStatus`` string (``"on"``/``"off"``…),
        unlike the radiator circuit's integer status.
    """

    flow_temperature_m2: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Flow Temperature M2 (Floor)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    flow_temperature_setpoint_m2: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Flow Temperature Setpoint M2 (Floor)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    pump_status_m2: str
    pump_speed_m2: Annotated[
        int,
        Field(
            json_schema_extra=_consumer(
                display_name="Pump Speed M2 (Floor)",
                unit="%",
                state_class="measurement",
                icon="mdi:pump",
            )
        ),
    ]
    frost_warning_m2: int
    frost_limit_m2: int
    operating_mode_m2: str
    operating_mode_economy_m2: str


@dataclass(frozen=True, slots=True)
class SystemState:
    """Vitotronic system status: storage, pumps, and switch valve."""

    storage_temperature_lowpass: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Storage Temperature (Low-pass)",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]
    internal_pump_status: str
    internal_pump_speed: Annotated[
        int,
        Field(
            json_schema_extra=_consumer(
                display_name="Internal Pump Speed",
                unit="%",
                state_class="measurement",
                icon="mdi:pump",
            )
        ),
    ]
    storage_charge_pump_status: str
    circulation_pump_status: str
    switch_valve_status: str
    flow_temperature_setpoint_m3: Annotated[
        float,
        Field(
            json_schema_extra=_consumer(
                display_name="Flow Temperature Setpoint M3",
                device_class="temperature",
                unit="°C",
                state_class="measurement",
            )
        ),
    ]


@dataclass(frozen=True, slots=True)
class DiagnosisState:
    """Diagnostic error status and the ten most recent error-history slots.

    Note:
        Fields mirror the signal-registry keys in ``SIGNAL_GROUPS['diagnosis']`` 1:1.
        Schema generation requires named properties rather than a collection type, so
        the flat numbered layout is intentional. Adding a slot requires updating both
        this class and ``SIGNAL_GROUPS['diagnosis']``.
    """

    error_status: str
    error_history_1: ErrorHistoryEntry
    error_history_2: ErrorHistoryEntry
    error_history_3: ErrorHistoryEntry
    error_history_4: ErrorHistoryEntry
    error_history_5: ErrorHistoryEntry
    error_history_6: ErrorHistoryEntry
    error_history_7: ErrorHistoryEntry
    error_history_8: ErrorHistoryEntry
    error_history_9: ErrorHistoryEntry
    error_history_10: ErrorHistoryEntry


GROUP_STATE_MODELS: dict[str, type[Any]] = {
    "outdoor": OutdoorState,
    "hot_water": HotWaterState,
    "burner": BurnerState,
    "heating_radiator": HeatingRadiatorState,
    "heating_floor": HeatingFloorState,
    "system": SystemState,
    "diagnosis": DiagnosisState,
}
"""Signal-group key → typed ``state_model`` used during registration."""
