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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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

    outdoor_temperature: float
    outdoor_temperature_lowpass: float
    outdoor_temperature_damped: float


@dataclass(frozen=True, slots=True)
class HotWaterState:
    """Domestic hot water temperature group payload (°C)."""

    hot_water_temperature: float
    hot_water_outlet_temperature: float


@dataclass(frozen=True, slots=True)
class BurnerState:
    """Burner temperatures, modulation, and runtime counters."""

    boiler_temperature: float
    boiler_temperature_lowpass: float
    boiler_temperature_setpoint: float
    exhaust_temperature: float
    burner_modulation: int
    burner_starts: int
    burner_hours_stage1: float
    plant_power_output: float


@dataclass(frozen=True, slots=True)
class HeatingRadiatorState:
    """Radiator heating circuit (M1) temperatures, pump, and modes.

    Note:
        ``pump_status_m1`` is an integer status code on this circuit, unlike
        the floor circuit's ``ReturnStatus`` string — the two circuits use
        different codec types.
    """

    flow_temperature_m1: float
    flow_temperature_setpoint_m1: float
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

    flow_temperature_m2: float
    flow_temperature_setpoint_m2: float
    pump_status_m2: str
    pump_speed_m2: int
    frost_warning_m2: int
    frost_limit_m2: int
    operating_mode_m2: str
    operating_mode_economy_m2: str


@dataclass(frozen=True, slots=True)
class SystemState:
    """Vitotronic system status: storage, pumps, and switch valve."""

    storage_temperature_lowpass: float
    internal_pump_status: str
    internal_pump_speed: int
    storage_charge_pump_status: str
    circulation_pump_status: str
    switch_valve_status: str
    flow_temperature_setpoint_m3: float


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
