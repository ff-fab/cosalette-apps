"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the consumer-metadata enrichment in the AsyncAPI schema: regenerating
the schema with ``cosalette schema init`` (or ``task gas2mqtt:schema:generate``)
strips the ``x-cosalette-consumer`` annotations, which would silently break HA
discovery. These tests fail loudly if that happens.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: schema enrichment must yield the documented HA entities
- Equivalence Partitioning: typed (device_class) vs untyped (counter) sensors
- Parametrize: all three enriched fields declared once, no duplication
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
    """Verify the enriched schema produces valid HA MQTT discovery payloads."""

    def test_generates_expected_enriched_sensors(
        self, ha_payloads: list[dict[str, Any]]
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
        object_ids = {p["config"]["object_id"] for p in ha_payloads}
        assert object_ids == expected

    def test_payloads_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor grouped under the gas2mqtt device.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in ha_payloads:
            assert payload["topic"].startswith("homeassistant/sensor/gas2mqtt/")
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_gas2mqtt"]

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
    def test_sensor_fields(
        self,
        ha_payloads: list[dict[str, Any]],
        object_id: str,
        expected_fields: dict[str, Any],
    ) -> None:
        """Each sensor carries the expected HA config fields.

        Technique: Equivalence Partitioning — typed (gas/temperature with
        device_class) vs untyped (counter: state_class only, no device_class).
        """
        config = next(
            (p["config"] for p in ha_payloads if p["config"]["object_id"] == object_id),
            None,
        )
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
