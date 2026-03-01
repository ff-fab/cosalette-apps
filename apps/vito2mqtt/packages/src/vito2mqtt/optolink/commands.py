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

"""Vitodens 200-W command registry.

Maps P300 memory addresses to signal names, data types, access modes,
and byte lengths for 89 commands across the following groups:

- Outdoor temperature, hot water, burner, heating circuit temperatures
- Heating characteristics, room setpoints, storage
- Pumps, timers (M1, M2, hot water, circulation pump)
- Frost warnings, operating modes, switch valve, diagnostics, system time

References:
    ADR-004 — Optolink Protocol Design
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccessMode(Enum):
    """Access mode for a boiler command.

    Controls whether a command supports reading from the boiler memory,
    writing to it, or both.

    - READ: Polling only — value is read from the boiler.
    - WRITE: Settable — value is written to the boiler (and may be read back).
    - READ_WRITE: Both directions supported.
    """

    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"


@dataclass(frozen=True, slots=True)
class Command:
    """A single Vitodens 200-W boiler command.

    Each command maps an English signal name to a 2-byte memory address
    with metadata describing the data format and access permissions.

    Attributes:
        name: English signal name, used as MQTT topic key (snake_case).
        address: 2-byte memory address (0x0000–0xFFFF).
        length: Data byte count (1, 2, 4, 8, or 9).
        type_code: Codec type code — one of the 11 supported types
            (IS10, IUNON, IU3600, PR2, PR3, BA, USV, ES, RT, CT, TI).
        access_mode: READ, WRITE, or READ_WRITE.
    """

    name: str
    address: int
    length: int
    type_code: str
    access_mode: AccessMode


# ---------------------------------------------------------------------------
# Private command list — all 89 Vitodens 200-W commands
# ---------------------------------------------------------------------------

_COMMANDS: list[Command] = [
    # -- Outdoor Temperature (3) -------------------------------------------
    Command("outdoor_temperature", 0x0800, 2, "IS10", AccessMode.READ),
    Command("outdoor_temperature_lowpass", 0x5525, 2, "IS10", AccessMode.READ),
    Command("outdoor_temperature_damped", 0x5527, 2, "IS10", AccessMode.READ),
    # -- Hot Water (4) -----------------------------------------------------
    Command("hot_water_temperature", 0x0804, 2, "IS10", AccessMode.READ),
    Command("hot_water_setpoint", 0x6300, 1, "IUNON", AccessMode.WRITE),
    Command("hot_water_outlet_temperature", 0x0814, 2, "IS10", AccessMode.READ),
    Command("hot_water_pump_overrun", 0x6762, 2, "IUNON", AccessMode.WRITE),
    # -- Burner (8) --------------------------------------------------------
    Command("boiler_temperature", 0x0802, 2, "IS10", AccessMode.READ),
    Command("boiler_temperature_lowpass", 0x0810, 2, "IS10", AccessMode.READ),
    Command("boiler_temperature_setpoint", 0x555A, 2, "IS10", AccessMode.READ),
    Command("exhaust_temperature", 0x0808, 2, "IS10", AccessMode.READ),
    Command("burner_modulation", 0x55D3, 1, "IUNON", AccessMode.READ),
    Command("burner_starts", 0x088A, 4, "IUNON", AccessMode.READ),
    Command("burner_hours_stage1", 0x08A7, 4, "IU3600", AccessMode.READ),
    Command("plant_power_output", 0xA38F, 2, "PR3", AccessMode.READ),
    # -- Heating Circuit Temperatures (5) ----------------------------------
    Command("flow_temperature_m1", 0x2900, 2, "IS10", AccessMode.READ),
    Command("flow_temperature_m2", 0x3900, 2, "IS10", AccessMode.READ),
    Command("flow_temperature_setpoint_m1", 0x2544, 2, "IS10", AccessMode.READ),
    Command("flow_temperature_setpoint_m2", 0x3544, 2, "IS10", AccessMode.READ),
    Command("flow_temperature_setpoint_m3", 0x4544, 2, "IS10", AccessMode.READ),
    # -- Heating Characteristics (4) ---------------------------------------
    # NOTE: IS10 with length=1 — the integration layer must pass
    # byte_length=cmd.length when encoding, since IS10 defaults to 2 bytes.
    Command("heating_curve_gradient_m1", 0x27D3, 1, "IS10", AccessMode.WRITE),
    Command("heating_curve_level_m1", 0x27D4, 2, "IUNON", AccessMode.WRITE),
    Command("heating_curve_gradient_m2", 0x37D3, 1, "IS10", AccessMode.WRITE),
    Command("heating_curve_level_m2", 0x37D4, 2, "IUNON", AccessMode.WRITE),
    # -- Room Setpoints (6) ------------------------------------------------
    Command("room_temperature_setpoint_m1", 0x2306, 1, "IUNON", AccessMode.WRITE),
    Command("room_temperature_setpoint_m2", 0x3306, 1, "IUNON", AccessMode.WRITE),
    Command(
        "room_temperature_setpoint_economy_m1", 0x2307, 1, "IUNON", AccessMode.WRITE
    ),
    Command(
        "room_temperature_setpoint_economy_m2", 0x3307, 1, "IUNON", AccessMode.WRITE
    ),
    Command("room_temperature_setpoint_party_m1", 0x2308, 1, "IUNON", AccessMode.WRITE),
    Command("room_temperature_setpoint_party_m2", 0x3308, 1, "IUNON", AccessMode.WRITE),
    # -- Storage (1) -------------------------------------------------------
    Command("storage_temperature_lowpass", 0x0812, 2, "IS10", AccessMode.READ),
    # -- Pumps (7) ---------------------------------------------------------
    Command("pump_status_m1", 0x7663, 1, "IUNON", AccessMode.READ),
    Command("pump_status_m2", 0x7665, 1, "RT", AccessMode.READ),
    Command("pump_speed_m2", 0x7665, 2, "PR2", AccessMode.READ),
    Command("internal_pump_status", 0x7660, 1, "RT", AccessMode.READ),
    Command("internal_pump_speed", 0x7660, 2, "PR2", AccessMode.READ),
    Command("storage_charge_pump_status", 0x6513, 1, "RT", AccessMode.READ),
    Command("circulation_pump_status", 0x6515, 1, "RT", AccessMode.READ),
    # -- Timers M1 (7) ----------------------------------------------------
    Command("timer_m1_monday", 0x2000, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_tuesday", 0x2008, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_wednesday", 0x2010, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_thursday", 0x2018, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_friday", 0x2020, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_saturday", 0x2028, 8, "CT", AccessMode.WRITE),
    Command("timer_m1_sunday", 0x2030, 8, "CT", AccessMode.WRITE),
    # -- Timers M2 (7) ----------------------------------------------------
    Command("timer_m2_monday", 0x3000, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_tuesday", 0x3008, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_wednesday", 0x3010, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_thursday", 0x3018, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_friday", 0x3020, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_saturday", 0x3028, 8, "CT", AccessMode.WRITE),
    Command("timer_m2_sunday", 0x3030, 8, "CT", AccessMode.WRITE),
    # -- Timers Hot Water (7) ----------------------------------------------
    Command("timer_hw_monday", 0x2100, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_tuesday", 0x2108, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_wednesday", 0x2110, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_thursday", 0x2118, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_friday", 0x2120, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_saturday", 0x2128, 8, "CT", AccessMode.WRITE),
    Command("timer_hw_sunday", 0x2130, 8, "CT", AccessMode.WRITE),
    # -- Timers Circulation Pump (7) ---------------------------------------
    Command("timer_cp_monday", 0x2200, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_tuesday", 0x2208, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_wednesday", 0x2210, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_thursday", 0x2218, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_friday", 0x2220, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_saturday", 0x2228, 8, "CT", AccessMode.WRITE),
    Command("timer_cp_sunday", 0x2230, 8, "CT", AccessMode.WRITE),
    # -- Frost (4) ---------------------------------------------------------
    Command("frost_warning_m1", 0x2500, 1, "IUNON", AccessMode.READ),
    Command("frost_warning_m2", 0x3500, 1, "IUNON", AccessMode.READ),
    Command("frost_limit_m1", 0x27A3, 1, "IUNON", AccessMode.READ),
    Command("frost_limit_m2", 0x37A3, 1, "IUNON", AccessMode.READ),
    # -- Operating Modes (6) -----------------------------------------------
    Command("operating_mode_m1", 0x2301, 1, "BA", AccessMode.READ),
    Command("operating_mode_m2", 0x3301, 1, "BA", AccessMode.READ),
    Command("operating_mode_economy_m1", 0x2302, 1, "BA", AccessMode.READ),
    Command("operating_mode_economy_m2", 0x3302, 1, "BA", AccessMode.READ),
    Command("operating_mode_party_m1", 0x2303, 1, "BA", AccessMode.WRITE),
    Command("operating_mode_party_m2", 0x3303, 1, "BA", AccessMode.WRITE),
    # -- Switch Valve (1) --------------------------------------------------
    Command("switch_valve_status", 0x0A10, 1, "USV", AccessMode.READ),
    # -- Diagnostics (11) --------------------------------------------------
    Command("error_status", 0x0A82, 1, "RT", AccessMode.READ),
    Command("error_history_1", 0x7507, 9, "ES", AccessMode.READ),
    Command("error_history_2", 0x7510, 9, "ES", AccessMode.READ),
    Command("error_history_3", 0x7519, 9, "ES", AccessMode.READ),
    Command("error_history_4", 0x7522, 9, "ES", AccessMode.READ),
    Command("error_history_5", 0x752B, 9, "ES", AccessMode.READ),
    Command("error_history_6", 0x7534, 9, "ES", AccessMode.READ),
    Command("error_history_7", 0x753D, 9, "ES", AccessMode.READ),
    Command("error_history_8", 0x7546, 9, "ES", AccessMode.READ),
    Command("error_history_9", 0x754F, 9, "ES", AccessMode.READ),
    Command("error_history_10", 0x7558, 9, "ES", AccessMode.READ),
    # -- System Time (1) ---------------------------------------------------
    Command("system_time", 0x088E, 8, "TI", AccessMode.WRITE),
]


# ---------------------------------------------------------------------------
# Public registry — dict keyed by signal name for O(1) lookup
# ---------------------------------------------------------------------------

COMMANDS: dict[str, Command] = {cmd.name: cmd for cmd in _COMMANDS}
"""Public registry of all 89 Vitodens 200-W commands, keyed by signal name."""


def lookup_by_address(address: int) -> list[Command]:
    """Return all commands matching a given memory address.

    Some addresses are shared by multiple commands (e.g., 0x7665 is used
    by both ``pump_status_m2`` and ``pump_speed_m2`` with different byte
    lengths and type codes). This function returns all matches.

    Args:
        address: 2-byte memory address (0x0000–0xFFFF).

    Returns:
        List of matching commands, or empty list if no match found.
    """
    return [cmd for cmd in _COMMANDS if cmd.address == address]
