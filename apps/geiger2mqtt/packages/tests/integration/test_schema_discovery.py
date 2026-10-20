"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery.

The ``x-cosalette-consumer`` metadata rides on the RadiationState fields and is
read here from the committed schema, so a dropped or distorted annotation
fails loudly. ``task geiger2mqtt:schema:check`` separately guards that the
committed file matches the registrations.

Lives in integration/ because it runs the schema CLI in a subprocess.

Test Techniques Used:
- Specification-based: three sensors with the documented units, state_class
  and icon, and no device_class (Home Assistant has none for radiation).
- Cross-check: every discovery state_topic is a topic the running app
  actually publishes, not a string derived from the same schema.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cosalette.testing import assert_discovery_topics_published

from ha_discovery import (
    configs_by_object_id,
    entities_without_bridge,
    load_ha_discovery_payloads,
)

from .conftest import STATE_TOPIC, make_harness, running

pytestmark = pytest.mark.integration

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"


@pytest.fixture(scope="module")
def ha_payloads() -> list[dict[str, Any]]:
    return load_ha_discovery_payloads(SCHEMA_PATH)


@pytest.fixture(scope="module")
def configs(ha_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return configs_by_object_id(entities_without_bridge(ha_payloads))


def test_exactly_three_sensors(configs: dict[str, dict[str, Any]]) -> None:
    assert set(configs) == {
        "radiation_cpm",
        "radiation_dose_rate",
        "radiation_dose_rate_avg",
    }


@pytest.mark.parametrize(
    ("object_id", "field", "unit"),
    [
        ("radiation_cpm", "cpm", "CPM"),
        ("radiation_dose_rate", "dose_rate", "µSv/h"),
        ("radiation_dose_rate_avg", "dose_rate_avg", "µSv/h"),
    ],
)
def test_sensor_config(
    configs: dict[str, dict[str, Any]], object_id: str, field: str, unit: str
) -> None:
    config = configs[object_id]

    assert config["unit_of_measurement"] == unit
    assert config["state_class"] == "measurement"
    assert config["icon"] == "mdi:radioactive"
    assert config["value_template"] == f"{{{{ value_json.{field} }}}}"
    assert config["state_topic"] == STATE_TOPIC
    assert "device_class" not in config


async def test_state_topics_are_published_at_runtime(
    ha_payloads: list[dict[str, Any]],
) -> None:
    """Technique: Cross-check — no phantom entity without a runtime publish."""
    harness = make_harness()

    async with running(harness):
        for _ in range(2):  # runs at 30 s and 60 s; the 60 s run publishes
            await harness.advance_time(30)
        await harness.wait_for_publish_count(STATE_TOPIC, 1)

    payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
    assert_discovery_topics_published(harness, payloads)
