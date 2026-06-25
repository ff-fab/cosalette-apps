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

    def test_generates_one_sensor_per_reading_field(
        self, ha_payloads: list[dict[str, Any]]
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
        object_ids = {p["config"]["object_id"] for p in ha_payloads}
        # Assert
        assert object_ids == expected

    def test_payloads_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor grouped under the airthings2mqtt device.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in ha_payloads:
            # Assert
            assert payload["topic"].startswith("homeassistant/sensor/airthings2mqtt/")
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_airthings2mqtt"]

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
    def test_sensor_fields(
        self,
        ha_payloads: list[dict[str, Any]],
        object_id: str,
        expected_fields: dict[str, Any],
    ) -> None:
        """Each sensor carries the expected HA config fields.

        Technique: Equivalence Partitioning — typed (temperature/humidity with
        device_class) vs untyped (radon: unit + state_class, no device_class).
        """
        # Arrange / Act
        config = next(
            (p["config"] for p in ha_payloads if p["config"]["object_id"] == object_id),
            None,
        )
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
