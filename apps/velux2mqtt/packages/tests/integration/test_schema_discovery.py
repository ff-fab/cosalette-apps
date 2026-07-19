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

"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the consumer-metadata enrichment in the AsyncAPI schema. The cover device
payload properties are hand-maintained (``@app.device`` does not accept a
``state_model`` in cosalette 0.5.5), so regenerating with ``cosalette schema init``
strips both the typed ``position`` property and its ``x-cosalette-consumer``
annotation — which would silently break HA discovery. This test fails loudly if
that happens.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"


@pytest.fixture(scope="module")
def ha_payloads() -> list[dict[str, Any]]:
    """Run the schema ha-discovery CLI once and return the parsed payloads."""
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify the enriched schema produces a valid HA MQTT discovery payload."""

    def test_generates_cover_position_sensor(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """The cover position field yields exactly one discovery payload.

        Technique: Specification-based — only the enriched position property
        is emitted.
        """
        object_ids = {p["config"]["object_id"] for p in ha_payloads}
        assert object_ids == {"cover_device_position"}

    def test_payload_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """The entity is a sensor grouped under the velux2mqtt device.

        Technique: Specification-based — HA device grouping contract.
        """
        payload = ha_payloads[0]
        assert payload["topic"].startswith("homeassistant/sensor/velux2mqtt/")
        assert payload["config"]["device"]["identifiers"] == ["cosalette_velux2mqtt"]

    def test_position_sensor_fields(self, ha_payloads: list[dict[str, Any]]) -> None:
        """The position sensor carries the expected HA config fields.

        Technique: Specification-based — position is a percentage measurement
        with no standard device_class.
        """
        config = ha_payloads[0]["config"]
        assert config["unit_of_measurement"] == "%"
        assert config["state_class"] == "measurement"
        assert config["value_template"] == "{{ value_json.position }}"
        assert config["icon"] == "mdi:window-shutter"
        # Cover position has no standard HA sensor device_class
        assert "device_class" not in config
