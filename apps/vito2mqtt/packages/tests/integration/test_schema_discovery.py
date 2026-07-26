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

"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery.

Verifies that the *committed* ``docs/schema.yaml`` yields exactly the expected
HA-discovery entities. The ``x-cosalette-consumer`` enrichment on the telemetry
payload models rides on the ``GROUP_STATE_MODELS`` fields via
``pydantic.Field(json_schema_extra=...)`` and is read here from the committed
schema; these tests fail loudly if it ever drops or distorts an annotation,
silently breaking HA discovery.

That the schema *regenerates* reproducibly from the models — so the committed
file can't drift from ``task vito2mqtt:schema:generate`` output — is guarded
separately by ``task vito2mqtt:schema:check``, not by these tests.

Shared-channel groups
---------------------
Both the *telemetry-only* signal groups (``outdoor``, ``burner``) and the
shared telemetry+command groups (``hot_water``, ``heating_radiator``,
``heating_floor``, ``system``) surface HA entities. The shared groups share
their MQTT topic with a command (ADR-002), so their generated payload is a
``oneOf[<StateModel>, {anyOf: [object, null]}]``. As of cosalette 0.5.6,
ha-discovery descends into ``oneOf``/``anyOf`` payload variants, so the
annotated properties inside the state-model variant now emit entities
alongside the top-level telemetry-only groups.

Note: Lives in integration/ because it spawns a subprocess and reads from
the filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: enriched schema must yield exactly the documented entities
- Equivalence Partitioning: temperature vs modulation/count/duration sensors
- Golden set: exact object_id set guards against both stripping and leakage
- Parametrize: per-sensor config fields declared once, no duplication
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

# The complete set of entities ha-discovery must emit. Kept exhaustive so the
# test fails if enrichment is stripped (fewer) or if an un-annotated field
# (a status/mode/frost signal) ever leaks through (more).
EXPECTED_OBJECT_IDS = {
    # Telemetry-only groups (top-level properties).
    "outdoor_outdoor_temperature",
    "outdoor_outdoor_temperature_lowpass",
    "outdoor_outdoor_temperature_damped",
    "burner_boiler_temperature",
    "burner_boiler_temperature_lowpass",
    "burner_boiler_temperature_setpoint",
    "burner_exhaust_temperature",
    "burner_burner_modulation",
    "burner_burner_starts",
    "burner_burner_hours_stage1",
    "burner_plant_power_output",
    # Shared telemetry+command groups — surfaced via 0.5.6 oneOf/anyOf
    # traversal of the shared-topic payload variants (ADR-002).
    "hot_water_hot_water_temperature",
    "hot_water_hot_water_outlet_temperature",
    "heating_radiator_flow_temperature_m1",
    "heating_radiator_flow_temperature_setpoint_m1",
    "heating_floor_flow_temperature_m2",
    "heating_floor_flow_temperature_setpoint_m2",
    "heating_floor_pump_speed_m2",
    "system_storage_temperature_lowpass",
    "system_internal_pump_speed",
    "system_flow_temperature_setpoint_m3",
}


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


@pytest.fixture(scope="module")
def configs_by_id(ha_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    object_ids = [p["config"]["object_id"] for p in ha_payloads]
    assert len(object_ids) == len(set(object_ids)), (
        f"Duplicate object_ids emitted: "
        f"{[x for x in object_ids if object_ids.count(x) > 1]}"
    )
    return {p["config"]["object_id"]: p["config"] for p in ha_payloads}


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify the enriched schema produces valid HA MQTT discovery payloads."""

    def test_emits_exactly_the_expected_entities(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The generated entity set matches the golden set exactly.

        Technique: Golden set — a superset means an un-annotated field
        leaked; a subset means enrichment is missing from the committed schema.
        """
        assert set(configs_by_id) == EXPECTED_OBJECT_IDS

    def test_payloads_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor grouped under the vito2mqtt device.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in ha_payloads:
            assert payload["topic"].startswith("homeassistant/sensor/vito2mqtt/")
            assert payload["config"]["device"]["identifiers"] == ["cosalette_vito2mqtt"]

    @pytest.mark.parametrize(
        "object_id, field",
        [
            ("outdoor_outdoor_temperature", "outdoor_temperature"),
            ("burner_boiler_temperature", "boiler_temperature"),
            ("burner_boiler_temperature_setpoint", "boiler_temperature_setpoint"),
            ("burner_exhaust_temperature", "exhaust_temperature"),
        ],
    )
    def test_temperature_sensors(
        self,
        configs_by_id: dict[str, dict[str, Any]],
        object_id: str,
        field: str,
    ) -> None:
        """Temperature sensors carry the standard temperature config.

        Technique: Equivalence Partitioning — representative temperature
        entities from both telemetry-only groups.
        """
        config = configs_by_id[object_id]
        assert config["device_class"] == "temperature"
        assert config["unit_of_measurement"] == "\u00b0C"
        assert config["state_class"] == "measurement"
        assert config["value_template"] == f"{{{{ value_json.{field} }}}}"

    @pytest.mark.parametrize(
        "object_id, expected",
        [
            (
                "burner_burner_modulation",
                {
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "icon": "mdi:fire",
                    "value_template": "{{ value_json.burner_modulation }}",
                },
            ),
            (
                "burner_burner_starts",
                {
                    "state_class": "total_increasing",
                    "icon": "mdi:fire",
                    "value_template": "{{ value_json.burner_starts }}",
                },
            ),
            (
                "burner_burner_hours_stage1",
                {
                    "device_class": "duration",
                    "unit_of_measurement": "h",
                    "state_class": "total_increasing",
                    "icon": "mdi:timer-outline",
                    "value_template": "{{ value_json.burner_hours_stage1 }}",
                },
            ),
            (
                "burner_plant_power_output",
                {
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "icon": "mdi:gauge",
                    "value_template": "{{ value_json.plant_power_output }}",
                },
            ),
        ],
    )
    def test_non_temperature_sensors(
        self,
        configs_by_id: dict[str, dict[str, Any]],
        object_id: str,
        expected: dict[str, Any],
    ) -> None:
        """Modulation, count, duration and power sensors carry their config.

        Technique: Equivalence Partitioning — one representative per
        non-temperature sensor shape.
        """
        config = configs_by_id[object_id]
        for key, value in expected.items():
            assert config.get(key) == value, (
                f"{object_id}: expected {key}={value!r}, got {config.get(key)!r}"
            )

    def test_burner_starts_has_no_unit(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """A bare counter omits unit and device_class.

        Technique: Specification-based — total_increasing counters without a
        unit must not fabricate one.
        """
        config = configs_by_id["burner_burner_starts"]
        assert "unit_of_measurement" not in config
        assert "device_class" not in config
