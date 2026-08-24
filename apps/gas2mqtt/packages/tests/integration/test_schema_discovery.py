"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Verifies that the *committed* ``docs/schema.yaml`` yields exactly the expected
HA-discovery entities. The ``x-cosalette-consumer`` enrichment rides on the
state-model fields via ``pydantic.Field(json_schema_extra=...)`` and is read
here from the committed schema; these tests fail loudly if it ever drops or
distorts an annotation, silently breaking HA discovery.

That the schema *regenerates* reproducibly from the models — so the committed
file can't drift from ``task gas2mqtt:schema:generate`` output — is guarded
separately by ``task gas2mqtt:schema:check``, not by these tests.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: schema enrichment must yield the documented HA entities
- Equivalence Partitioning: typed (device_class) vs untyped (counter) sensors
- Parametrize: all three enriched fields declared once, no duplication
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
from cosalette import MockMqttClient
from cosalette._schema._consumer_gen import HaDiscoveryPayload
from cosalette.testing import assert_discovery_topics_published

from gas2mqtt.settings import Gas2MqttSettings

from .conftest import HarnessView, build_full_integration_app, run_app_briefly

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"
BRIDGE_OBJECT_ID = "bridge"  # ADR-058 synthetic bridge sentinel


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
    gas2mqtt entity, so it is asserted once in its own test and excluded from
    the per-entity expectations here.
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

    def test_generates_expected_enriched_sensors(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """The three enriched fields yield discovery payloads.

        Technique: Specification-based — only properties carrying
        x-cosalette-consumer are emitted (trigger is intentionally omitted).
        """
        expected = {
            "gas_counter_consumption_m3",
            "gas_counter_counter",
            "temperature_temperature",
        }
        object_ids = {p["config"]["object_id"] for p in entity_payloads}
        assert object_ids == expected
        for payload in entity_payloads:
            assert "unique_id" in payload["config"]

    def test_payloads_grouped_under_per_device_ha_devices(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """Each entity sits on its own physical device, linked to the bridge.

        cosalette 0.6.2 (ADR-058) models each resolved device as its own HA
        device linked to the app bridge via ``via_device``, replacing the
        single app-wide device earlier releases emitted. gas2mqtt resolves two
        devices — the counter and the temperature probe.

        Technique: Specification-based — HA device grouping contract.
        """
        identifiers = set()
        for payload in entity_payloads:
            assert payload["topic"].startswith("homeassistant/sensor/gas2mqtt/")
            device = payload["config"]["device"]
            assert device["via_device"] == "cosalette_gas2mqtt"
            identifiers.add(device["identifiers"][0])
        assert identifiers == {
            "cosalette_gas2mqtt_gas_counter",
            "cosalette_gas2mqtt_temperature",
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
            "homeassistant/binary_sensor/gas2mqtt/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"
        assert config["device"]["identifiers"] == ["cosalette_gas2mqtt"]

    @pytest.mark.parametrize(
        "object_id, expected_fields",
        [
            (
                "gas_counter_consumption_m3",
                {
                    "device_class": "gas",
                    "unit_of_measurement": "m³",
                    "state_class": "total_increasing",
                    "value_template": "{{ value_json.consumption_m3 }}",
                },
            ),
            (
                "gas_counter_counter",
                {
                    "state_class": "total_increasing",
                    "value_template": "{{ value_json.counter }}",
                },
            ),
            (
                "temperature_temperature",
                {
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.temperature }}",
                },
            ),
        ],
    )
    def test_sensor_config_fields_match_enrichment_annotations(
        self,
        configs_by_id: dict[str, dict[str, Any]],
        object_id: str,
        expected_fields: dict[str, Any],
    ) -> None:
        """Each sensor carries the expected HA config fields.

        Technique: Equivalence Partitioning — typed (gas/temperature with
        device_class) vs untyped (counter: state_class only, no device_class).
        """
        config = configs_by_id.get(object_id)
        assert config is not None, f"No payload found for object_id={object_id!r}"
        for key, value in expected_fields.items():
            assert config.get(key) == value, (
                f"{object_id}: expected {key}={value!r}, got {config.get(key)!r}"
            )
        # Untyped sensors (counter) must NOT carry device_class
        if "device_class" not in expected_fields:
            assert "device_class" not in config, (
                f"{object_id}: unexpected device_class={config.get('device_class')!r}"
            )


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify HA-discovery state_topics match runtime-published topics."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        Runs the real handler registrations (gas_counter, temperature) via
        ``build_full_integration_app`` — hardware substituted with
        ``FakeMagnetometer``, everything else identical to
        ``gas2mqtt.main.create_app()`` — and cross-checks each HA-discovery
        payload's ``state_topic`` against the topics actually published at
        runtime. A state_topic with no matching runtime publish would ship a
        phantom HA entity (cap-5f8).

        The check itself is the framework helper ``assert_discovery_topics_published``
        (adopted per monorepo ADR-004 / cap-6y0), fed the CLI-generated payloads
        re-wrapped as ``HaDiscoveryPayload`` — the exact type the helper and the
        runtime publisher carry. gas2mqtt drives raw ``App`` + ``MockMqttClient``
        rather than :class:`AppHarness`, so the mock is adapted via
        :class:`~conftest.HarnessView`.

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        test_app = build_full_integration_app()
        mock_mqtt = MockMqttClient()
        await run_app_briefly(test_app, mock_mqtt, Gas2MqttSettings())

        payloads = [
            HaDiscoveryPayload(topic=p["topic"], config=p["config"])
            for p in ha_payloads
        ]
        assert_discovery_topics_published(HarnessView(mock_mqtt), payloads)
