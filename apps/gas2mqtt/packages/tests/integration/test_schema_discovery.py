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
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from cosalette import MockMqttClient

from gas2mqtt.settings import Gas2MqttSettings

from .conftest import build_full_integration_app, run_app_briefly

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
        payload's ``state_topic`` against ``mock_mqtt.published``, the set
        of topics actually published at runtime. A state_topic with no
        matching runtime publish would ship a phantom HA entity (cap-5f8).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        test_app = build_full_integration_app()
        mock_mqtt = MockMqttClient()
        await run_app_briefly(test_app, mock_mqtt, Gas2MqttSettings())

        published_topics = {topic for topic, *_ in mock_mqtt.published}
        for payload in ha_payloads:
            state_topic = payload["config"]["state_topic"]
            assert state_topic in published_topics, (
                f"state_topic {state_topic!r} was never published at "
                f"runtime; published topics: {sorted(published_topics)}"
            )
