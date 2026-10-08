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

"""Unit tests for deployment defaults.

Test Techniques Used:
- Specification-based: compose arms the loop-stall watchdog with an overridable
  value recorded in docs/configuration.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_APP_DIR = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_compose_arms_loop_stall_watchdog() -> None:
    """Unexpected event-loop stalls exit after 120 seconds by default.

    Technique: Specification-based — this backstop detects a blocked event loop
    that cannot refresh the native health file.
    """
    compose = yaml.safe_load((_APP_DIR / "compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["wallpanel-control"]["environment"]

    assert environment["COSALETTE_LOOP_STALL_TIMEOUT"] == (
        "${COSALETTE_LOOP_STALL_TIMEOUT:-120}"
    )
