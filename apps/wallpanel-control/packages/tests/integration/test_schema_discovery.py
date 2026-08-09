"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the consumer-metadata enrichment in the AsyncAPI schema: regenerating
the schema with ``cosalette schema init`` (or
``task wallpanel-control:schema:generate``) strips the ``x-cosalette-consumer``
annotations, which would silently break HA discovery. These tests fail loudly
if that happens.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: schema enrichment must yield the documented HA entities
- Equivalence Partitioning: numeric (brightness %) vs enum (display state) sensors
- Parametrize: both enriched display fields declared once, no duplication
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
from cosalette.testing import AppHarness

from .conftest import DISPLAY_SET, run_with_commands

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

    def test_generates_enriched_display_sensors(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Only the enriched display fields yield discovery payloads.

        Technique: Specification-based — system/action is command-ack only and
        carries no x-cosalette-consumer, so it produces no HA entity.
        """
        expected = {"display_brightness_percent", "display_state"}
        object_ids = {p["config"]["object_id"] for p in ha_payloads}
        assert object_ids == expected

    def test_payloads_grouped_under_app_device(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """Every entity is a sensor grouped under the wallpanel-control device.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in ha_payloads:
            assert payload["topic"].startswith(
                "homeassistant/sensor/wallpanel_control/"
            )
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_wallpanel_control"]

    @pytest.mark.parametrize(
        "object_id, expected_fields",
        [
            (
                "display_brightness_percent",
                {
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "icon": "mdi:brightness-percent",
                    "value_template": "{{ value_json.brightness_percent }}",
                },
            ),
            (
                "display_state",
                {
                    "icon": "mdi:monitor",
                    "value_template": "{{ value_json.state }}",
                },
            ),
        ],
    )
    def test_sensor_fields(
        self,
        configs_by_id: dict[str, dict[str, Any]],
        object_id: str,
        expected_fields: dict[str, Any],
    ) -> None:
        """Each sensor carries the expected HA config fields.

        Technique: Equivalence Partitioning — numeric measurement (brightness)
        vs plain enum text (state, no unit/state_class).
        """
        config = configs_by_id.get(object_id)
        assert config is not None, f"No payload found for object_id={object_id!r}"
        for key, value in expected_fields.items():
            assert config.get(key) == value, (
                f"{object_id}: expected {key}={value!r}, got {config.get(key)!r}"
            )

    def test_display_state_is_plain_text_sensor(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """display_state carries no numeric-measurement metadata.

        Technique: Equivalence Partitioning — locks the boundary between the
        plain enum-text sensor (state) and the numeric-measurement sensor
        (brightness). Mirrors the airthings radon negative guard: a regression
        adding spurious device_class/unit/state_class to the text sensor must
        fail loudly.
        """
        config = configs_by_id.get("display_state")
        assert config is not None, "No payload found for object_id='display_state'"
        for key in ("device_class", "unit_of_measurement", "state_class"):
            assert key not in config, (
                f"display_state: unexpected {key}={config.get(key)!r} "
                "on a plain-text sensor"
            )


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify HA-discovery state_topics match runtime-published topics."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]], harness: AppHarness
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        wallpanel-control's ``display`` command only publishes state after
        an accepted command (no periodic polling), so this drives one real
        command through the integration-test ``harness``
        (``FakeWallpanel``/``FakeWol`` substituted for SSH/WoL I/O) and
        cross-checks each HA-discovery payload's ``state_topic`` against
        ``harness.mqtt.published``, the set of topics actually published at
        runtime. A state_topic with no matching runtime publish would ship
        a phantom HA entity (cap-5f8).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_with_commands(harness, [(DISPLAY_SET, {"state": "on"})])

        published_topics = {topic for topic, *_ in harness.mqtt.published}
        for payload in ha_payloads:
            state_topic = payload["config"]["state_topic"]
            assert state_topic in published_topics, (
                f"state_topic {state_topic!r} was never published at "
                f"runtime; published topics: {sorted(published_topics)}"
            )
