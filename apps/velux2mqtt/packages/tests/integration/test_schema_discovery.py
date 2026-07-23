"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the model-driven consumer metadata in the AsyncAPI schema. The cover
device state is typed via ``@app.device(state_model=CoverState)`` (cosalette
0.5.6), and ``CoverState.position`` carries its ``x-cosalette-consumer``
annotation through ``pydantic.Field(json_schema_extra=...)``. So
``cosalette schema init`` emits both the typed ``position`` property and its
consumer metadata automatically — no hand-maintained schema block. This test
fails loudly if a schema regeneration ever stops producing the documented HA
cover entity.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the model-driven schema must yield the documented HA cover entity
- Boundary Value Analysis: position has no standard device_class; absence is asserted
- Structural: guard that regeneration still emits the typed, enriched position property
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
