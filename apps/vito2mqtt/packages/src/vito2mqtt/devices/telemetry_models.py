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

Each frozen dataclass is the value returned by the corresponding
telemetry handler (see :mod:`vito2mqtt.devices.telemetry`), which
constructs it from the group's serialized signal values. Wiring these as
``state_model=`` on ``app.add_telemetry`` makes
``cosalette schema init`` emit *typed* payload properties instead of a
bare ``type: object``.  Typed properties can then carry
``x-cosalette-consumer`` metadata that drives Home Assistant MQTT
discovery (device_class, unit, state_class, …).

Design notes
------------
- ``state_model`` is the runtime contract as well as the schema one: since
  cosalette 0.9.0 (ADR-068) it outranks the handler's return annotation and
  every returned value is validated against it, so a group whose fields
  drift from :data:`~vito2mqtt.devices.SIGNAL_GROUPS` publishes
  ``ReturnValidationError`` to the error topic instead of state. Each
  handler returns an instance of its group's model and its return
  annotation is set to that same model (cap-z02), so the two agree.
- Field types match the *serialized* form (post
  :func:`~vito2mqtt.devices._serialization.serialize_value`), not the raw
  codec types.  Notably ``ReturnStatus`` signals serialize to ``str``;
  ES (error-history) signals serialize to a ``{"error", "timestamp"}``
  dict that the handler's :class:`~pydantic.TypeAdapter` coerces into an
  :class:`ErrorHistoryEntry` when it builds the model.
- :data:`GROUP_STATE_MODELS` maps each signal-group key to its model so the
  registration loop can look models up by group name.

Consumer-metadata maintenance (model-driven)
--------------------------------------------
The ``x-cosalette-consumer`` metadata that drives HA discovery
(device_class, unit, state_class, icon, …) rides on each surfaced field
via :func:`pydantic.Field`'s ``json_schema_extra`` (built through the
framework :func:`cosalette.schema.consumer` helper). Because cosalette
generates the schema with
``TypeAdapter(model).json_schema()``, which preserves ``json_schema_extra``,
this enrichment *survives* ``task vito2mqtt:schema:generate`` — no
post-generation hand-application step. This mirrors velux2mqtt's
``CoverState``. The migration away from hand-authored ``docs/schema.yaml``
enrichment is tracked as bead ``cap-g90``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from cosalette.schema import consumer
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


def _temperature(display_name: str) -> dict[str, Any]:
    """``x-cosalette-consumer`` for a standard °C measurement sensor.

    Collapses the ``device_class="temperature"``, ``unit="°C"``,
    ``state_class="measurement"`` triple shared by the many temperature
    fields, where only the ``display_name`` varies.
    """

    return consumer(
        display_name=display_name,
        device_class="temperature",
        unit="°C",
        state_class="measurement",
    )


def _percent(display_name: str, *, icon: str | None = None) -> dict[str, Any]:
    """``x-cosalette-consumer`` for a percentage measurement sensor.

    Shared by the modulation / pump-speed / power fields (``unit="%"``,
    ``state_class="measurement"``). ``icon`` is optional and omitted from the
    emitted metadata when not supplied, so output matches a hand-written block
    exactly.
    """

    if icon is None:
        return consumer(display_name=display_name, unit="%", state_class="measurement")
    return consumer(
        display_name=display_name,
        unit="%",
        state_class="measurement",
        icon=icon,
    )


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
        float, Field(json_schema_extra=_temperature("Outdoor Temperature"))
    ]
    outdoor_temperature_lowpass: Annotated[
        float, Field(json_schema_extra=_temperature("Outdoor Temperature (Low-pass)"))
    ]
    outdoor_temperature_damped: Annotated[
        float, Field(json_schema_extra=_temperature("Outdoor Temperature (Damped)"))
    ]


@dataclass(frozen=True, slots=True)
class HotWaterState:
    """Domestic hot water temperature group payload (°C)."""

    hot_water_temperature: Annotated[
        float, Field(json_schema_extra=_temperature("Hot Water Temperature"))
    ]
    hot_water_outlet_temperature: Annotated[
        float, Field(json_schema_extra=_temperature("Hot Water Outlet Temperature"))
    ]


@dataclass(frozen=True, slots=True)
class BurnerState:
    """Burner temperatures, modulation, and runtime counters."""

    boiler_temperature: Annotated[
        float, Field(json_schema_extra=_temperature("Boiler Temperature"))
    ]
    boiler_temperature_lowpass: Annotated[
        float, Field(json_schema_extra=_temperature("Boiler Temperature (Low-pass)"))
    ]
    boiler_temperature_setpoint: Annotated[
        float, Field(json_schema_extra=_temperature("Boiler Temperature Setpoint"))
    ]
    exhaust_temperature: Annotated[
        float, Field(json_schema_extra=_temperature("Exhaust Temperature"))
    ]
    burner_modulation: Annotated[
        int, Field(json_schema_extra=_percent("Burner Modulation", icon="mdi:fire"))
    ]
    burner_starts: Annotated[
        int,
        Field(
            json_schema_extra=consumer(
                display_name="Burner Starts",
                state_class="total_increasing",
                icon="mdi:fire",
            )
        ),
    ]
    burner_hours_stage1: Annotated[
        float,
        Field(
            json_schema_extra=consumer(
                display_name="Burner Hours (Stage 1)",
                device_class="duration",
                unit="h",
                state_class="total_increasing",
                icon="mdi:timer-outline",
            )
        ),
    ]
    # float, not int: the PR3 codec is (first byte / 2), so an odd raw byte
    # decodes to a half-percent value (e.g. 20.5). An int field would reject
    # that under state_model validation and publish ReturnValidationError.
    plant_power_output: Annotated[
        float, Field(json_schema_extra=_percent("Plant Power Output", icon="mdi:gauge"))
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
        float, Field(json_schema_extra=_temperature("Flow Temperature M1 (Radiator)"))
    ]
    flow_temperature_setpoint_m1: Annotated[
        float,
        Field(
            json_schema_extra=_temperature("Flow Temperature Setpoint M1 (Radiator)")
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
        float, Field(json_schema_extra=_temperature("Flow Temperature M2 (Floor)"))
    ]
    flow_temperature_setpoint_m2: Annotated[
        float,
        Field(json_schema_extra=_temperature("Flow Temperature Setpoint M2 (Floor)")),
    ]
    pump_status_m2: str
    pump_speed_m2: Annotated[
        int, Field(json_schema_extra=_percent("Pump Speed M2 (Floor)", icon="mdi:pump"))
    ]
    frost_warning_m2: int
    frost_limit_m2: int
    operating_mode_m2: str
    operating_mode_economy_m2: str


@dataclass(frozen=True, slots=True)
class SystemState:
    """Vitotronic system status: storage, pumps, and switch valve."""

    storage_temperature_lowpass: Annotated[
        float, Field(json_schema_extra=_temperature("Storage Temperature (Low-pass)"))
    ]
    internal_pump_status: str
    internal_pump_speed: Annotated[
        int, Field(json_schema_extra=_percent("Internal Pump Speed", icon="mdi:pump"))
    ]
    storage_charge_pump_status: str
    circulation_pump_status: str
    switch_valve_status: str
    flow_temperature_setpoint_m3: Annotated[
        float, Field(json_schema_extra=_temperature("Flow Temperature Setpoint M3"))
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
