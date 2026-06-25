"""Unit tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the consumer-metadata enrichment in the AsyncAPI schema: regenerating
the schema with ``cosalette schema init`` (or ``task airthings2mqtt:schema:generate``)
strips the ``x-cosalette-consumer`` annotations, which would silently break HA
discovery. These tests fail loudly if that happens.

Test Techniques Used:
- Specification-based: schema enrichment must yield the documented HA entities
- Equivalence Partitioning: typed (device_class) vs untyped (radon) sensors
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# apps/airthings2mqtt/packages/tests/unit/<file> -> app root is parents[3]
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


@pytest.mark.unit
class TestHaDiscoveryGeneration:
    """Verify the enriched schema produces valid HA MQTT discovery payloads."""

    def test_generates_one_sensor_per_reading_field(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """All four AirthingsReading fields yield a discovery payload."""
        object_ids = {p["config"]["object_id"] for p in ha_payloads}
        assert object_ids == {
            "airthings_temperature",
            "airthings_humidity",
            "airthings_radon_24h_avg",
            "airthings_radon_long_term_avg",
        }

    def test_payloads_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor grouped under the airthings2mqtt device."""
        for payload in ha_payloads:
            assert payload["topic"].startswith("homeassistant/sensor/airthings2mqtt/")
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_airthings2mqtt"]

    def test_temperature_carries_device_class_and_unit(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Typed sensor: temperature maps to HA device_class + unit + state_class."""
        config = next(
            p["config"]
            for p in ha_payloads
            if p["config"]["object_id"] == "airthings_temperature"
        )
        assert config["device_class"] == "temperature"
        assert config["unit_of_measurement"] == "°C"
        assert config["state_class"] == "measurement"
        assert config["state_topic"] == "airthings2mqtt/airthings/state"
        assert config["value_template"] == "{{ value_json.temperature }}"

    def test_radon_uses_unit_without_device_class(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Untyped sensor: radon has no HA device_class but keeps unit + state_class."""
        config = next(
            p["config"]
            for p in ha_payloads
            if p["config"]["object_id"] == "airthings_radon_24h_avg"
        )
        assert "device_class" not in config
        assert config["unit_of_measurement"] == "Bq/m³"
        assert config["state_class"] == "measurement"
