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
``heating_floor``, ``system``) surface HA entities. A shared group's command
half writes the same MQTT namespace (ADR-002) but is a *void* handler, so it
emits no ``/state`` channel of its own and the group's payload is the plain
state model rather than a ``oneOf`` with the command's return type.

That is load-bearing, not incidental. The command half is registered
``discoverable="state"``: its ``/set`` channel is not an HA entity, while the
paired telemetry ``/state`` channel remains discoverable. The handlers remain
void as an independent wire-contract guarantee: they must not add a second
``/state`` payload that merges with telemetry.
``test_command_channels_keep_only_state_discoverable`` locks the discovery
outcome; ``test_command_halves_emit_no_state_channel`` locks the void-handler
contract.

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

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cosalette.testing import AppHarness, assert_discovery_topics_published

from ha_discovery import (
    BRIDGE_OBJECT_ID,
    configs_by_object_id,
    entities_without_bridge,
    load_ha_discovery_payloads,
)

from .conftest import run_app_briefly

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
    # Shared telemetry+command groups. The command half is void and opted out
    # of discovery, so these come from the telemetry half alone (ADR-002).
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
    return load_ha_discovery_payloads(SCHEMA_PATH)


@pytest.fixture(scope="module")
def entity_payloads(ha_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discovery payloads for the app's own entities, without the bridge."""
    return entities_without_bridge(ha_payloads)


@pytest.fixture(scope="module")
def configs_by_id(entity_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    return configs_by_object_id(entity_payloads)


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
        HA-discovery payload's ``state_topic`` against the topics actually
        published at runtime. A state_topic with no matching runtime publish
        would ship a phantom HA entity (cap-5f8).

        The check itself is the framework helper ``assert_discovery_topics_published``
        (adopted per monorepo ADR-004 / cap-6y0), fed the CLI-generated payloads
        wrapped as ``SimpleNamespace`` objects (duck-typed;
        ``assert_discovery_topics_published`` only accesses
        ``.config.get('state_topic')``). This also re-verifies that every
        shared telemetry+command group entity (oneOf/anyOf traversal)
        maps to a real runtime topic.

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_app_briefly(harness)

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(harness, payloads)


@pytest.mark.integration
class TestDiscoveryOptOut:
    """Lock which channels are opted out of consumer discovery (ADR-073).

    ``cosalette schema check`` compares registered device names only; it never
    reads ``x-cosalette-discoverable``. Without these assertions a flag flip is
    invisible to CI in either direction — a lost sensor shows up only as a
    golden-set mismatch, and a lost opt-out not at all.

    Test Techniques Used:
    - Specification-based: assert the committed schema against the documented
      per-channel intent rather than against regenerated output.
    - Golden set: the exact opted-out channel set, so both a stripped and a
      leaked flag fail.
    """

    @pytest.fixture(scope="class")
    def schema_channels(self) -> dict[str, Any]:
        """Parse the committed schema and return its channels mapping."""
        import yaml

        document = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
        channels: dict[str, Any] = document["channels"]
        return channels

    def test_opted_out_channels_are_exactly_the_documented_set(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """Only /set channels and the two diagnostic feeds opt out."""
        opted_out = {
            name
            for name, channel in schema_channels.items()
            if channel.get("x-cosalette-discoverable") is False
        }
        assert opted_out == {
            # /set channels are not HA entities. Their paired /state channels
            # remain discoverable through discoverable="state".
            "hot_waterCommand",
            "heating_radiatorCommand",
            "heating_floorCommand",
            "systemCommand",
            # Raw Optolink signal values for troubleshooting, not entities.
            "diagnosisState",
            # Long-running disinfection device, driven by its own schedule.
            "legionellaState",
        }

    @pytest.mark.parametrize(
        ("command_channel", "state_channel"),
        [
            ("hot_waterCommand", "hot_waterState"),
            ("heating_radiatorCommand", "heating_radiatorState"),
            ("heating_floorCommand", "heating_floorState"),
            ("systemCommand", "systemState"),
        ],
    )
    def test_command_channels_keep_only_state_discoverable(
        self,
        schema_channels: dict[str, Any],
        command_channel: str,
        state_channel: str,
    ) -> None:
        """Every command opts out only its /set channel, not paired telemetry.

        ``discoverable="state"`` must resolve to ``false`` on the command
        channel and leave telemetry state discoverable in the committed schema.
        Checking the rendered extension, rather than registration metadata,
        catches regressions in channel-level resolution (ADR-073/ADR-074).
        """
        assert schema_channels[command_channel].get("x-cosalette-discoverable") is False
        state = schema_channels[state_channel]
        assert state.get("x-cosalette-discoverable") is not False, (
            f"{state_channel} was opted out of discovery; {command_channel} "
            "must keep only its paired telemetry state discoverable."
        )

    @pytest.mark.parametrize(
        "group", ["hot_water", "heating_radiator", "heating_floor", "system"]
    )
    def test_command_halves_emit_no_state_channel(
        self, schema_channels: dict[str, Any], group: str
    ) -> None:
        """The command handlers stay void as an independent wire-contract guard.

        Asserts the mechanism directly: a merged command ``/state`` channel
        shows up as a ``oneOf`` payload on the telemetry channel.
        """
        payload = schema_channels[f"{group}State"]["messages"]["message"]["payload"]
        assert "oneOf" not in payload, (
            f"{group}Command emitted a /state channel and merged into "
            f"{group}State. The command handler must remain void so it does "
            "not publish a competing state payload."
        )
