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

"""Unit tests for devices/__init__.py — Command group registry.

Test Techniques Used:
- Specification-based: Verify registry matches command definitions
- Cross-reference: Every signal in COMMAND_GROUPS must exist in COMMANDS
- Invariant Checking: All grouped signals are writable
- Structural: Groups are tuples (immutable), no duplicates
"""

from __future__ import annotations

import pytest

from vito2mqtt.devices import COMMAND_GROUPS, SIGNAL_GROUPS
from vito2mqtt.optolink.codec import _ENCODE_UNSUPPORTED
from vito2mqtt.optolink.commands import COMMANDS, AccessMode

# ---------------------------------------------------------------------------
# Helpers — collect all (group, signal) pairs for parametrize
# ---------------------------------------------------------------------------

_ALL_COMMAND_SIGNALS = [
    (group, signal) for group, signals in COMMAND_GROUPS.items() for signal in signals
]

_EXPECTED_GROUPS = {"hot_water", "heating_radiator", "heating_floor", "system"}


# ---------------------------------------------------------------------------
# Command Group Integrity
# ---------------------------------------------------------------------------


class TestCommandGroupsIntegrity:
    """Verify COMMAND_GROUPS is consistent with the COMMANDS registry."""

    @pytest.mark.parametrize(
        ("group", "signal"),
        _ALL_COMMAND_SIGNALS,
        ids=[f"{g}/{s}" for g, s in _ALL_COMMAND_SIGNALS],
    )
    def test_all_signals_exist_in_commands_registry(
        self, group: str, signal: str
    ) -> None:
        """Every signal in COMMAND_GROUPS must be a key in COMMANDS.

        Technique: Cross-reference — registry ↔ groups.
        """
        assert signal in COMMANDS, (
            f"Signal '{signal}' in group '{group}' not found in COMMANDS"
        )

    @pytest.mark.parametrize(
        ("group", "signal"),
        _ALL_COMMAND_SIGNALS,
        ids=[f"{g}/{s}" for g, s in _ALL_COMMAND_SIGNALS],
    )
    def test_all_signals_are_writable(self, group: str, signal: str) -> None:
        """Every grouped signal must have WRITE or READ_WRITE access mode.

        Technique: Specification-based — groups are for commanding.
        """
        cmd = COMMANDS[signal]
        assert cmd.access_mode in {AccessMode.WRITE, AccessMode.READ_WRITE}, (
            f"Signal '{signal}' in group '{group}' has "
            f"access_mode={cmd.access_mode}, expected WRITE or READ_WRITE"
        )

    def test_all_four_groups_present(self) -> None:
        """COMMAND_GROUPS must contain exactly the 4 expected domain groups.

        Technique: Specification-based — matches writable domains.
        """
        assert set(COMMAND_GROUPS.keys()) == _EXPECTED_GROUPS

    def test_no_duplicate_signals_across_groups(self) -> None:
        """No signal name may appear in more than one command group.

        Technique: Invariant — each signal belongs to exactly one domain.
        """
        seen: dict[str, str] = {}
        for group, signals in COMMAND_GROUPS.items():
            for signal in signals:
                assert signal not in seen, (
                    f"Signal '{signal}' appears in both '{seen[signal]}' and '{group}'"
                )
                seen[signal] = group

    def test_signals_are_tuples(self) -> None:
        """Each group's signal collection must be a tuple for immutability.

        Technique: Structural — prevents accidental mutation.
        """
        for group, signals in COMMAND_GROUPS.items():
            assert isinstance(signals, tuple), (
                f"Group '{group}' signals should be tuple, got {type(signals)}"
            )

    def test_no_overlap_with_telemetry_signal_names(self) -> None:
        """Overlapping signals between command and telemetry groups must be READ_WRITE.

        WRITE-only signals must not appear in telemetry groups.
        READ_WRITE signals may legitimately appear in both registries.

        Technique: Cross-reference — command vs. telemetry separation.
        """
        telemetry_signals = {
            signal for signals in SIGNAL_GROUPS.values() for signal in signals
        }
        command_signals = {
            signal for signals in COMMAND_GROUPS.values() for signal in signals
        }
        overlap = telemetry_signals & command_signals
        for signal in overlap:
            assert COMMANDS[signal].access_mode == AccessMode.READ_WRITE, (
                f"Signal {signal!r} overlaps command and telemetry groups "
                f"but is not READ_WRITE (got {COMMANDS[signal].access_mode})"
            )

    def test_all_writable_commands_are_covered(self) -> None:
        """Every encodable WRITE/READ_WRITE command must appear in a group.

        Signals whose type_code is in ``_ENCODE_UNSUPPORTED`` are
        excluded — they cannot be written until codec encoding is
        implemented for their type.

        Technique: Specification-based — completeness check.
        """
        # Arrange
        writable_names = {
            name
            for name, cmd in COMMANDS.items()
            if cmd.access_mode in {AccessMode.WRITE, AccessMode.READ_WRITE}
            and cmd.type_code not in _ENCODE_UNSUPPORTED
        }
        grouped_names = {
            signal for signals in COMMAND_GROUPS.values() for signal in signals
        }

        # Act / Assert
        missing = writable_names - grouped_names
        assert not missing, f"Writable commands not in any COMMAND_GROUP: {missing}"
        extra = grouped_names - writable_names
        assert not extra, f"COMMAND_GROUPS signals that are not writable: {extra}"
