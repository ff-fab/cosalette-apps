"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the consumer-metadata enrichment in the AsyncAPI schema: regenerating
the schema with ``cosalette schema init`` (or ``task airthings2mqtt:schema:generate``)
strips the ``x-cosalette-consumer`` annotations, which would silently break HA
discovery. These tests fail loudly if that happens.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: schema enrichment must yield the documented HA entities
- Equivalence Partitioning: typed (device_class) vs untyped (radon) sensors
- Parametrize: all four sensor fields declared once, no duplication
- Cross-check: every state_topic is verified against topics the
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

    def test_generates_one_sensor_per_reading_field(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """All four AirthingsReading fields yield a discovery payload.

        Technique: Specification-based — count matches schema properties.
        """
        # Arrange
        expected = {
            "airthings_temperature",
            "airthings_humidity",
            "airthings_radon_24h_avg",
            "airthings_radon_long_term_avg",
        }
        # Act
        object_ids = {p["config"]["object_id"] for p in entity_payloads}
        # Assert
        assert object_ids == expected
        for payload in entity_payloads:
            assert "unique_id" in payload["config"]

    def test_payloads_grouped_under_app_device(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor on the per-device ``airthings`` HA device.

        cosalette 0.6.2 (ADR-058) models each resolved device as its own HA
        device linked to the app bridge via ``via_device``, replacing the
        single app-wide device earlier releases emitted.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in entity_payloads:
            # Assert
            assert payload["topic"].startswith("homeassistant/sensor/airthings2mqtt/")
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_airthings2mqtt_airthings"]
            assert device["via_device"] == "cosalette_airthings2mqtt"

    def test_emits_app_bridge_entity(self, ha_payloads: list[dict[str, Any]]) -> None:
        """A single diagnostic bridge entity materialises the app device.

        Technique: Specification-based — ADR-058 bridge contract. Without it
        the ``via_device`` link on every real entity dangles, because
        ``via_device`` alone does not create a device in HA's registry.
        """
        bridges = [
            p for p in ha_payloads if p["config"]["object_id"] == BRIDGE_OBJECT_ID
        ]
        # Assert
        assert len(bridges) == 1
        config = bridges[0]["config"]
        assert bridges[0]["topic"] == (
            "homeassistant/binary_sensor/airthings2mqtt/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"
        assert config["device"]["identifiers"] == ["cosalette_airthings2mqtt"]

    @pytest.mark.parametrize(
        "object_id, expected_fields",
        [
            (
                "airthings_temperature",
                {
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.temperature }}",
                },
            ),
            (
                "airthings_humidity",
                {
                    "device_class": "humidity",
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.humidity }}",
                },
            ),
            (
                "airthings_radon_24h_avg",
                {
                    "unit_of_measurement": "Bq/m³",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.radon_24h_avg }}",
                },
            ),
            (
                "airthings_radon_long_term_avg",
                {
                    "unit_of_measurement": "Bq/m³",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.radon_long_term_avg }}",
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

        Technique: Equivalence Partitioning — typed (temperature/humidity with
        device_class) vs untyped (radon: unit + state_class, no device_class).
        """
        # Arrange / Act
        config = configs_by_id.get(object_id)
        # Assert
        assert config is not None, f"No payload found for object_id={object_id!r}"
        for key, value in expected_fields.items():
            assert config.get(key) == value, (
                f"{object_id}: expected {key}={value!r}, got {config.get(key)!r}"
            )
        # Untyped sensors (radon) must NOT carry device_class
        if "device_class" not in expected_fields:
            assert "device_class" not in config, (
                f"{object_id}: unexpected device_class={config.get('device_class')!r}"
            )


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify HA-discovery state_topics match runtime-published topics."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]], harness: AppHarness
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        Runs the real ``airthings`` telemetry registration via the
        integration-test ``harness`` (``FakeAirthingsReader`` substituted
        for BLE hardware) and cross-checks each HA-discovery payload's
        ``state_topic`` against the topics actually published at runtime.
        A state_topic with no matching runtime publish would ship a
        phantom HA entity.

        The check itself is the framework helper ``assert_discovery_topics_published``
        (adopted per monorepo ADR-004 fed the CLI-generated payloads
        wrapped as ``SimpleNamespace`` objects (duck-typed;
        ``assert_discovery_topics_published`` only accesses
        ``.config.get('state_topic')``).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_app_briefly(harness)

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(harness, payloads)
