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

"""Unit tests for devices/__init__.py — Signal group registry.

Test Techniques Used:
- Specification-based: Verify registry matches command definitions
- Cross-reference: Every signal in SIGNAL_GROUPS must exist in COMMANDS
- Invariant Checking: All grouped signals are readable, none write-only
- Structural: Groups are tuples (immutable), no duplicates across groups
"""

from __future__ import annotations

import pytest

from vito2mqtt.devices import SIGNAL_GROUPS
from vito2mqtt.optolink.commands import COMMANDS, AccessMode

# ---------------------------------------------------------------------------
# Helpers — collect all (group, signal) pairs for parametrize
# ---------------------------------------------------------------------------

_ALL_SIGNALS = [
    (group, signal) for group, signals in SIGNAL_GROUPS.items() for signal in signals
]

_EXPECTED_GROUPS = {
    "outdoor",
    "hot_water",
    "burner",
    "heating_radiator",
    "heating_floor",
    "system",
    "diagnosis",
}


# ---------------------------------------------------------------------------
# Signal Group Integrity
# ---------------------------------------------------------------------------


class TestSignalGroupsIntegrity:
    """Verify SIGNAL_GROUPS is consistent with the COMMANDS registry."""

    @pytest.mark.parametrize(
        ("group", "signal"),
        _ALL_SIGNALS,
        ids=[f"{g}/{s}" for g, s in _ALL_SIGNALS],
    )
    def test_all_signals_exist_in_commands_registry(
        self, group: str, signal: str
    ) -> None:
        """Every signal in SIGNAL_GROUPS must be a key in COMMANDS.

        Technique: Cross-reference — registry ↔ groups.
        """
        assert signal in COMMANDS, (
            f"Signal '{signal}' in group '{group}' not found in COMMANDS"
        )

    @pytest.mark.parametrize(
        ("group", "signal"),
        _ALL_SIGNALS,
        ids=[f"{g}/{s}" for g, s in _ALL_SIGNALS],
    )
    def test_all_signals_are_readable(self, group: str, signal: str) -> None:
        """Every grouped signal must have READ or READ_WRITE access mode.

        Technique: Specification-based — groups are for polling.
        """
        cmd = COMMANDS[signal]
        assert cmd.access_mode in {AccessMode.READ, AccessMode.READ_WRITE}, (
            f"Signal '{signal}' in group '{group}' has "
            f"access_mode={cmd.access_mode}, expected READ or READ_WRITE"
        )

    def test_all_seven_groups_present(self) -> None:
        """SIGNAL_GROUPS must contain exactly the 7 expected domain groups.

        Technique: Specification-based — matches ADR-005 polling domains.
        """
        assert set(SIGNAL_GROUPS.keys()) == _EXPECTED_GROUPS

    def test_no_duplicate_signals_across_groups(self) -> None:
        """No signal name may appear in more than one group.

        Technique: Invariant — each signal belongs to exactly one domain.
        """
        seen: dict[str, str] = {}
        for group, signals in SIGNAL_GROUPS.items():
            for signal in signals:
                assert signal not in seen, (
                    f"Signal '{signal}' appears in both '{seen[signal]}' and '{group}'"
                )
                seen[signal] = group

    def test_signals_are_tuples(self) -> None:
        """Each group's signal collection must be a tuple for immutability.

        Technique: Structural — prevents accidental mutation.
        """
        for group, signals in SIGNAL_GROUPS.items():
            assert isinstance(signals, tuple), (
                f"Group '{group}' signals should be tuple, got {type(signals)}"
            )
