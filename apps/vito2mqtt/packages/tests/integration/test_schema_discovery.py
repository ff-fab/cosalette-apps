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
- Cross-check (cap-5f8): every state_topic is verified against topics the
  real app (fakes for hardware only) actually publishes at runtime, not just
  a string independently derived from the same schema.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cosalette.testing import AppHarness

from .conftest import run_app_briefly

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"
BRIDGE_OBJECT_ID = "bridge"  # ADR-058 synthetic bridge sentinel

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
        env={
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONSTARTUP", "PYTHONHOME"}
        },
    )
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def entity_payloads(ha_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discovery payloads for the app's own entities, without the bridge.

    cosalette 0.6.2 (ADR-058) emits one synthetic per-app ``bridge``
    binary_sensor so Home Assistant materialises the device every real entity
    links to via ``via_device``. It is framework plumbing rather than a
    vito2mqtt datapoint, so it is asserted once in its own test and kept out
    of the golden entity set here.
    """
    return [p for p in ha_payloads if p["config"]["object_id"] != BRIDGE_OBJECT_ID]


@pytest.fixture(scope="module")
def configs_by_id(entity_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    object_ids = [p["config"]["object_id"] for p in entity_payloads]
    assert len(object_ids) == len(set(object_ids)), (
        f"Duplicate object_ids emitted: "
        f"{[x for x in object_ids if object_ids.count(x) > 1]}"
    )
    return {p["config"]["object_id"]: p["config"] for p in entity_payloads}


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
        for config in configs_by_id.values():
            assert "unique_id" in config

    def test_payloads_grouped_under_per_device_ha_devices(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """Each entity sits on its own subsystem device, linked to the bridge.

        cosalette 0.6.2 (ADR-058) models each resolved device as its own HA
        device linked to the app bridge via ``via_device``, replacing the
        single app-wide device earlier releases emitted. vito2mqtt resolves
        one per heating subsystem.

        Technique: Specification-based — HA device grouping contract.
        """
        identifiers = set()
        for payload in entity_payloads:
            assert payload["topic"].startswith("homeassistant/sensor/vito2mqtt/")
            device = payload["config"]["device"]
            assert device["via_device"] == "cosalette_vito2mqtt"
            identifiers.add(device["identifiers"][0])
        assert identifiers == {
            f"cosalette_vito2mqtt_{d}"
            for d in (
                "burner",
                "heating_floor",
                "heating_radiator",
                "hot_water",
                "outdoor",
                "system",
            )
        }

    def test_emits_app_bridge_entity(self, ha_payloads: list[dict[str, Any]]) -> None:
        """A single diagnostic bridge entity materialises the app device.

        Technique: Specification-based — ADR-058 bridge contract. Without it
        the ``via_device`` link on every real entity dangles, because
        ``via_device`` alone does not create a device in HA's registry.
        """
        bridges = [
            p for p in ha_payloads if p["config"]["object_id"] == BRIDGE_OBJECT_ID
        ]
        assert len(bridges) == 1
        config = bridges[0]["config"]
        assert bridges[0]["topic"] == (
            "homeassistant/binary_sensor/vito2mqtt/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"
        assert config["device"]["identifiers"] == ["cosalette_vito2mqtt"]

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


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify HA-discovery state_topics match runtime-published topics."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]], harness: AppHarness
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        Runs the real telemetry/command group registrations via the
        integration-test ``harness`` (``FakeOptolinkAdapter`` substituted
        for the serial Optolink connection) and cross-checks each
        HA-discovery payload's ``state_topic`` against
        ``harness.mqtt.published``, the set of topics actually published
        at runtime. A state_topic with no matching runtime publish would
        ship a phantom HA entity (cap-5f8).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_app_briefly(harness)

        published_topics = {topic for topic, *_ in harness.mqtt.published}
        for payload in ha_payloads:
            state_topic = payload["config"]["state_topic"]
            assert state_topic in published_topics, (
                f"state_topic {state_topic!r} was never published at "
                f"runtime; published topics: {sorted(published_topics)}"
            )
