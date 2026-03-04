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

"""Telemetry device definitions, signal group and command group registries."""

from __future__ import annotations

__all__ = ["SIGNAL_GROUPS", "COMMAND_GROUPS"]

SIGNAL_GROUPS: dict[str, tuple[str, ...]] = {
    "outdoor": (
        "outdoor_temperature",
        "outdoor_temperature_lowpass",
        "outdoor_temperature_damped",
    ),
    "hot_water": (
        "hot_water_temperature",
        "hot_water_outlet_temperature",
    ),
    "burner": (
        "boiler_temperature",
        "boiler_temperature_lowpass",
        "boiler_temperature_setpoint",
        "exhaust_temperature",
        "burner_modulation",
        "burner_starts",
        "burner_hours_stage1",
        "plant_power_output",
    ),
    "heating_radiator": (
        "flow_temperature_m1",
        "flow_temperature_setpoint_m1",
        "pump_status_m1",
        "frost_warning_m1",
        "frost_limit_m1",
        "operating_mode_m1",
        "operating_mode_economy_m1",
    ),
    "heating_floor": (
        "flow_temperature_m2",
        "flow_temperature_setpoint_m2",
        "pump_status_m2",
        "pump_speed_m2",
        "frost_warning_m2",
        "frost_limit_m2",
        "operating_mode_m2",
        "operating_mode_economy_m2",
    ),
    "system": (
        "storage_temperature_lowpass",
        "internal_pump_status",
        "internal_pump_speed",
        "storage_charge_pump_status",
        "circulation_pump_status",
        "switch_valve_status",
        "flow_temperature_setpoint_m3",
    ),
    "diagnosis": (
        "error_status",
        "error_history_1",
        "error_history_2",
        "error_history_3",
        "error_history_4",
        "error_history_5",
        "error_history_6",
        "error_history_7",
        "error_history_8",
        "error_history_9",
        "error_history_10",
    ),
}

COMMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "hot_water": (
        "hot_water_setpoint",
        "hot_water_pump_overrun",
        "timer_hw_monday",
        "timer_hw_tuesday",
        "timer_hw_wednesday",
        "timer_hw_thursday",
        "timer_hw_friday",
        "timer_hw_saturday",
        "timer_hw_sunday",
    ),
    "heating_radiator": (
        "heating_curve_gradient_m1",
        "heating_curve_level_m1",
        "room_temperature_setpoint_m1",
        "room_temperature_setpoint_economy_m1",
        "room_temperature_setpoint_party_m1",
        "operating_mode_party_m1",
        "timer_m1_monday",
        "timer_m1_tuesday",
        "timer_m1_wednesday",
        "timer_m1_thursday",
        "timer_m1_friday",
        "timer_m1_saturday",
        "timer_m1_sunday",
    ),
    "heating_floor": (
        "heating_curve_gradient_m2",
        "heating_curve_level_m2",
        "room_temperature_setpoint_m2",
        "room_temperature_setpoint_economy_m2",
        "room_temperature_setpoint_party_m2",
        "operating_mode_party_m2",
        "timer_m2_monday",
        "timer_m2_tuesday",
        "timer_m2_wednesday",
        "timer_m2_thursday",
        "timer_m2_friday",
        "timer_m2_saturday",
        "timer_m2_sunday",
    ),
    "system": (
        "timer_cp_monday",
        "timer_cp_tuesday",
        "timer_cp_wednesday",
        "timer_cp_thursday",
        "timer_cp_friday",
        "timer_cp_saturday",
        "timer_cp_sunday",
    ),
}
