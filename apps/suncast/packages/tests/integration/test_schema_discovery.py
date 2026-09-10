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

"""Integration tests for docs/schema.yaml — consumer discovery intent.

suncast emits no Home Assistant entities. Its single ``shadow`` channel
publishes a rendered SVG image reference rather than a scalar datapoint, so it
carries no ``x-cosalette-consumer`` annotations and nothing to discover.

Before cosalette 0.9.4 that state was implicit and untested. 0.9.4 evaluates the
discovery gate per channel, so a consumer-visible channel emitting no entity is
an error; ``shadow`` is registered ``discoverable=False`` to declare the absence
deliberately. These tests lock both halves — the declaration in the committed
schema, and the empty-but-successful CLI result it produces. Neither is covered
by ``task suncast:schema:check``, which compares registered device names only
and never reads ``x-cosalette-discoverable``.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: assert the committed schema against documented intent.
- Golden set: the exact opted-out channel set, so a stripped flag and a leaked
  flag both fail.
- Error Guessing: an app that emits no entities is exactly the case where a
  silent regression to exit 1 would go unnoticed.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from ha_discovery import run_ha_discovery

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"


@pytest.fixture(scope="module")
def ha_discovery_run() -> subprocess.CompletedProcess[str]:
    """Run the schema ha-discovery CLI once and return the completed process.

    suncast expects an empty payload list, so this keeps the raw process
    rather than the parsed payloads the sibling apps assert on.
    """
    return run_ha_discovery(SCHEMA_PATH)


@pytest.fixture(scope="module")
def schema_channels() -> dict[str, Any]:
    """Parse the committed schema and return its channels mapping."""
    document = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
    channels: dict[str, Any] = document["channels"]
    return channels


@pytest.mark.integration
class TestDiscoveryOptOut:
    """The committed schema declares the discovery exclusion explicitly."""

    def test_opted_out_channels_are_exactly_the_documented_set(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """``shadowState`` is the only channel opted out of discovery."""
        opted_out = {
            name
            for name, channel in schema_channels.items()
            if channel.get("x-cosalette-discoverable") is False
        }
        assert opted_out == {"shadowState"}

    def test_shadow_channel_carries_no_consumer_annotations(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """The opt-out matches reality: there is nothing to discover.

        Guards against the opposite mistake — annotating a field and leaving
        the opt-out in place, which would hide a real entity.
        """
        payload = json.dumps(schema_channels["shadowState"])
        assert "x-cosalette-consumer" not in payload


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """The CLI succeeds and emits nothing."""

    def test_cli_exits_zero(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """A declared exclusion satisfies the per-channel gate.

        Regression guard: without ``discoverable=False`` the 0.9.4 gate fails
        with "consumer-visible channel(s) produce no discovery entities".
        """
        assert ha_discovery_run.returncode == 0, (
            f"ha-discovery exited {ha_discovery_run.returncode}:\n"
            f"{ha_discovery_run.stderr}"
        )

    def test_emits_no_payloads(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """Not even the ADR-058 bridge entity: an excluded app emits nothing."""
        assert json.loads(ha_discovery_run.stdout) == []
