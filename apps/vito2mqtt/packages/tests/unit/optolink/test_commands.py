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

"""Unit tests for optolink/commands.py — Vitodens 200-W command registry.

Test Techniques Used:
- Specification-based Testing: Verify Command dataclass contracts (frozen, hashable)
- Equivalence Partitioning: Type codes, access modes, address ranges via @parametrize
- Boundary Value Analysis: Address range limits (0x0000–0xFFFF)
- Error Guessing: Duplicate names, unknown addresses, address collisions
- Decision Table: Spot-check specific commands against known specifications
"""

from __future__ import annotations

import re

import pytest

from vito2mqtt.optolink.commands import (
    COMMANDS,
    AccessMode,
    Command,
    lookup_by_address,
)

# Allowed type codes per ADR-004 / codec.py
VALID_TYPE_CODES = frozenset(
    {"IS10", "IUNON", "IU3600", "PR2", "PR3", "BA", "USV", "ES", "RT", "CT", "TI"}
)

# Allowed data lengths per P300 protocol
VALID_LENGTHS = frozenset({1, 2, 4, 8, 9})

# snake_case pattern: starts with lowercase letter, then lowercase/digits/underscores
SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# =============================================================================
# Tests
# =============================================================================


class TestCommandModel:
    """Tests for Command dataclass invariants.

    Technique: Specification-based Testing — verifying frozen dataclass
    contracts including immutability, hashability, equality, and repr.
    """

    def test_command_is_frozen(self) -> None:
        """Frozen dataclass rejects attribute assignment.

        Technique: Specification-based — frozen=True contract.
        """
        cmd = Command("test", 0x0800, 2, "IS10", AccessMode.READ)
        with pytest.raises(AttributeError):
            cmd.name = "modified"  # type: ignore[misc]

    def test_command_is_hashable(self) -> None:
        """Frozen dataclass is hashable, usable as dict key or set member.

        Technique: Specification-based — frozen=True implies __hash__.
        """
        cmd = Command("test", 0x0800, 2, "IS10", AccessMode.READ)
        # Should not raise — set insertion requires hashability
        assert {cmd} == {cmd}

    def test_access_mode_has_exactly_three_members(self) -> None:
        """AccessMode enum has READ, WRITE, READ_WRITE — no more, no less.

        Technique: Specification-based — enum completeness.
        """
        assert len(AccessMode) == 3
        assert set(AccessMode) == {
            AccessMode.READ,
            AccessMode.WRITE,
            AccessMode.READ_WRITE,
        }

    def test_command_equality_based_on_all_fields(self) -> None:
        """Two commands with identical fields are equal; differing fields are not.

        Technique: Specification-based — dataclass __eq__ uses all fields.
        """
        cmd_a = Command("test", 0x0800, 2, "IS10", AccessMode.READ)
        cmd_b = Command("test", 0x0800, 2, "IS10", AccessMode.READ)
        cmd_c = Command("test", 0x0800, 2, "IS10", AccessMode.WRITE)
        assert cmd_a == cmd_b
        assert cmd_a != cmd_c

    def test_command_uses_slots(self) -> None:
        """Frozen dataclass with slots=True has no __dict__.

        Technique: Specification-based — slots=True eliminates per-instance
        dict, saving memory and preventing dynamic attribute assignment.
        """
        cmd = Command("test", 0x0800, 2, "IS10", AccessMode.READ)
        assert not hasattr(cmd, "__dict__")

    def test_command_repr_includes_key_fields(self) -> None:
        """Command repr includes the signal name and address for debuggability.

        Technique: Specification-based — dataclass auto-generates __repr__.
        """
        cmd = Command("outdoor_temperature", 0x0800, 2, "IS10", AccessMode.READ)
        r = repr(cmd)
        assert "outdoor_temperature" in r
        assert "0x0800" in r or "2048" in r
        assert "IS10" in r


class TestCommandRegistry:
    """Tests for the COMMANDS registry dict invariants.

    Technique: Equivalence Partitioning + Error Guessing — validating
    structural invariants across the entire registry.
    """

    def test_registry_has_89_commands(self) -> None:
        """Registry contains exactly 89 commands.

        Technique: Specification-based — expected count from command list.
        """
        assert len(COMMANDS) == 89

    def test_all_names_are_snake_case(self) -> None:
        """Every command name matches ^[a-z][a-z0-9_]*$.

        Technique: Equivalence Partitioning — naming convention.
        """
        for name in COMMANDS:
            assert SNAKE_CASE_RE.match(name), f"{name!r} is not snake_case"

    def test_all_type_codes_are_supported(self) -> None:
        """Every command uses one of the 11 supported type codes.

        Technique: Equivalence Partitioning — valid type code set.
        """
        for name, cmd in COMMANDS.items():
            assert cmd.type_code in VALID_TYPE_CODES, (
                f"{name}: unknown type_code {cmd.type_code!r}"
            )

    def test_all_addresses_fit_in_two_bytes(self) -> None:
        """Every address is in range 0x0000–0xFFFF.

        Technique: Boundary Value Analysis — 16-bit address space.
        """
        for name, cmd in COMMANDS.items():
            assert 0x0000 <= cmd.address <= 0xFFFF, (
                f"{name}: address {cmd.address:#06x} out of 16-bit range"
            )

    def test_all_lengths_are_valid(self) -> None:
        """Every data length is 1, 2, 4, 8, or 9.

        Technique: Equivalence Partitioning — valid length set.
        """
        for name, cmd in COMMANDS.items():
            assert cmd.length in VALID_LENGTHS, f"{name}: invalid length {cmd.length}"

    def test_no_duplicate_command_names(self) -> None:
        """dict keys are unique by construction, but verify name field matches key.

        Technique: Error Guessing — detect copy-paste mistakes.
        """
        seen: set[str] = set()
        for name, _cmd in COMMANDS.items():
            assert name not in seen, f"duplicate name: {name}"
            seen.add(name)

    def test_key_matches_command_name_field(self) -> None:
        """Every dict key equals the Command.name attribute.

        Technique: Error Guessing — detect key/name mismatch from typos.
        """
        for key, cmd in COMMANDS.items():
            assert key == cmd.name, f"key {key!r} != cmd.name {cmd.name!r}"

    def test_all_access_modes_are_valid(self) -> None:
        """Every command uses a valid AccessMode enum member.

        Technique: Equivalence Partitioning — enum membership.
        """
        for name, cmd in COMMANDS.items():
            assert isinstance(cmd.access_mode, AccessMode), (
                f"{name}: access_mode is not AccessMode"
            )

    def test_type_codes_cover_all_eleven(self) -> None:
        """Registry uses all 11 supported type codes at least once.

        Technique: Equivalence Partitioning — full coverage of codec types.
        """
        used_codes = {cmd.type_code for cmd in COMMANDS.values()}
        assert used_codes == VALID_TYPE_CODES

    def test_all_commands_are_command_instances(self) -> None:
        """Every registry value is a Command instance.

        Technique: Specification-based — type safety.
        """
        for name, cmd in COMMANDS.items():
            assert isinstance(cmd, Command), f"{name}: not a Command instance"


class TestLookupByAddress:
    """Tests for lookup_by_address() helper function.

    Technique: Equivalence Partitioning — single-match, multi-match,
    and no-match address classes.
    """

    def test_known_unique_address_returns_single_command(self) -> None:
        """Address 0x0800 maps to exactly one command: outdoor_temperature.

        Technique: Specification-based — known unique address.
        """
        results = lookup_by_address(0x0800)
        assert len(results) == 1
        assert results[0].name == "outdoor_temperature"

    def test_shared_address_0x7665_returns_two_commands(self) -> None:
        """Address 0x7665 is shared by pump_status_m2 and pump_speed_m2.

        Technique: Equivalence Partitioning — shared address class.
        """
        results = lookup_by_address(0x7665)
        names = {cmd.name for cmd in results}
        assert len(results) == 2
        assert names == {"pump_status_m2", "pump_speed_m2"}

    def test_shared_address_0x7660_returns_two_commands(self) -> None:
        """Address 0x7660 is shared by internal_pump_status and internal_pump_speed.

        Technique: Equivalence Partitioning — second shared address.
        """
        results = lookup_by_address(0x7660)
        names = {cmd.name for cmd in results}
        assert len(results) == 2
        assert names == {"internal_pump_status", "internal_pump_speed"}

    def test_unknown_address_returns_empty_list(self) -> None:
        """Address 0xDEAD has no commands — returns empty list.

        Technique: Error Guessing — nonexistent address.
        """
        assert lookup_by_address(0xDEAD) == []

    def test_address_0x0808_returns_exhaust_temperature_only(self) -> None:
        """Address 0x0808 has only exhaust_temperature (no collision).

        The legacy return_temperature_17a was excluded to avoid the 0x0808
        collision. Verify only one command exists at this address.

        Technique: Error Guessing — verify deliberate collision avoidance.
        """
        results = lookup_by_address(0x0808)
        assert len(results) == 1
        assert results[0].name == "exhaust_temperature"


class TestSpecificCommands:
    """Spot-check specific important commands against known specifications.

    Technique: Decision Table — verify address, length, type_code, and
    access_mode for representative commands from each category.
    """

    @pytest.mark.parametrize(
        ("name", "address", "length", "type_code", "access_mode"),
        [
            pytest.param(
                "outdoor_temperature",
                0x0800,
                2,
                "IS10",
                AccessMode.READ,
                id="outdoor_temperature",
            ),
            pytest.param(
                "hot_water_setpoint",
                0x6300,
                1,
                "IUNON",
                AccessMode.READ_WRITE,
                id="hot_water_setpoint",
            ),
            pytest.param(
                "burner_starts",
                0x088A,
                4,
                "IUNON",
                AccessMode.READ,
                id="burner_starts",
            ),
            pytest.param(
                "burner_hours_stage1",
                0x08A7,
                4,
                "IU3600",
                AccessMode.READ,
                id="burner_hours_stage1",
            ),
            pytest.param(
                "operating_mode_m1",
                0x2301,
                1,
                "BA",
                AccessMode.READ,
                id="operating_mode_m1",
            ),
            pytest.param(
                "system_time",
                0x088E,
                8,
                "TI",
                AccessMode.WRITE,
                id="system_time",
            ),
            pytest.param(
                "error_history_1",
                0x7507,
                9,
                "ES",
                AccessMode.READ,
                id="error_history_1",
            ),
            pytest.param(
                "switch_valve_status",
                0x0A10,
                1,
                "USV",
                AccessMode.READ,
                id="switch_valve_status",
            ),
            pytest.param(
                "plant_power_output",
                0xA38F,
                2,
                "PR3",
                AccessMode.READ,
                id="plant_power_output",
            ),
            pytest.param(
                "pump_speed_m2",
                0x7665,
                2,
                "PR2",
                AccessMode.READ,
                id="pump_speed_m2",
            ),
            pytest.param(
                "timer_m1_monday",
                0x2000,
                8,
                "CT",
                AccessMode.READ_WRITE,
                id="timer_m1_monday",
            ),
        ],
    )
    def test_command_matches_spec(
        self,
        name: str,
        address: int,
        length: int,
        type_code: str,
        access_mode: AccessMode,
    ) -> None:
        """Command {name} matches its expected specification.

        Technique: Decision Table — cross-reference against data sheet.
        """
        cmd = COMMANDS[name]
        assert cmd.address == address
        assert cmd.length == length
        assert cmd.type_code == type_code
        assert cmd.access_mode == access_mode


class TestAccessModeDistribution:
    """Tests for access mode distribution across command categories.

    Technique: Equivalence Partitioning — verifying categorical
    invariants (all timers are WRITE, all error_history are READ).
    """

    def test_read_and_write_counts(self) -> None:
        """Registry has expected counts of READ, WRITE, and READ_WRITE commands.

        Technique: Specification-based — distribution check.
        After read-before-write: 46 READ, 1 WRITE (system_time), 42 READ_WRITE.
        """
        read_count = sum(
            1 for cmd in COMMANDS.values() if cmd.access_mode == AccessMode.READ
        )
        write_count = sum(
            1 for cmd in COMMANDS.values() if cmd.access_mode == AccessMode.WRITE
        )
        rw_count = sum(
            1 for cmd in COMMANDS.values() if cmd.access_mode == AccessMode.READ_WRITE
        )
        assert read_count == 46
        assert write_count == 1
        assert rw_count == 42
        assert read_count + write_count + rw_count == 89

    def test_all_timer_commands_are_read_write(self) -> None:
        """Every timer_* command has AccessMode.READ_WRITE.

        Timers support read-before-write to avoid redundant EEPROM writes.

        Technique: Equivalence Partitioning — timer category invariant.
        """
        timer_cmds = [
            cmd for name, cmd in COMMANDS.items() if name.startswith("timer_")
        ]
        assert len(timer_cmds) == 28  # 7 days × 4 groups
        for cmd in timer_cmds:
            assert cmd.access_mode == AccessMode.READ_WRITE, (
                f"{cmd.name} should be READ_WRITE"
            )

    def test_all_error_history_commands_are_read(self) -> None:
        """Every error_history_* command has AccessMode.READ.

        Technique: Equivalence Partitioning — error history category invariant.
        """
        error_cmds = [
            cmd for name, cmd in COMMANDS.items() if name.startswith("error_history_")
        ]
        assert len(error_cmds) == 10
        for cmd in error_cmds:
            assert cmd.access_mode == AccessMode.READ, f"{cmd.name} should be READ"
