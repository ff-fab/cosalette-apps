"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

``app.device`` is registered with a callable ``name=`` (``_cover_map`` in
:mod:`velux2mqtt.main`, keyed off user-configured ``settings.covers``). A
plain ``cosalette schema init``/``check`` would collapse every real per-cover
device (``blind``, ``window``, ...) into a single channel named after the
Python handler's qualname (``cover_device``), which is why
``task velux2mqtt:schema:generate`` instead runs ``cosalette schema dump
--resolve-settings`` (ADR-051) against the checked-in ``.env.schema``
profile before writing ``docs/schema.yaml`` — expanding the NameSpec into
real per-cover channels (``blindState``, ``windowState``, ...). With those
real channels, ``CoverState.position``'s ``x-cosalette-consumer`` annotation
(see :class:`velux2mqtt.devices.cover.CoverState`) now produces one discovery
payload per configured cover, with ``state_topic`` matching the real runtime
topic (``velux2mqtt/{cover.name}/state``, e.g. ``velux2mqtt/blind/state`` —
see ``docs/mqtt-topics.md``) rather than the qualname channel
``velux2mqtt/cover_device/state`` that produced a phantom entity before this
fix .

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: every payload must describe a real, currently
  configured cover with a matching real runtime state_topic
- Cross-check: every state_topic is verified against topics the
  real app (fakes for hardware only) actually publishes at runtime — not a
  regex pattern independently derived from documentation. The prior
  regex-based regression guard would have passed even if the real cover
  names had diverged from docs/mqtt-topics.md; this replaces it with the
  same technique 's own fix should have used.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from cosalette.testing import AppHarness, assert_discovery_topics_published

from ha_discovery import (
    BRIDGE_OBJECT_ID,
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


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify HA MQTT discovery generation emits real, per-cover entities."""

    def test_generates_one_payload_per_configured_cover(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """One discovery payload is generated per cover in .env.schema.

        ``docs/schema.yaml`` is generated via ``cosalette schema dump
        --resolve-settings`` against the checked-in ``.env.schema`` profile
        (``task velux2mqtt:schema:generate``), which expands the
        ``_cover_map`` NameSpec into real per-cover channels. This test
        pins the count to that profile's two covers (``blind``, ``window``);
        update it alongside ``.env.schema`` if the profile's cover count
        changes.

        Technique: Specification-based — the resolved schema must yield
        exactly one HA entity per configured cover.
        """
        assert len(entity_payloads) == 2
        for payload in entity_payloads:
            assert "unique_id" in payload["config"]

    def test_emits_app_bridge_entity(self, ha_payloads: list[dict[str, Any]]) -> None:
        """A single diagnostic bridge entity materialises the app device.

        Technique: Specification-based — ADR-058 bridge contract. Without it
        the ``via_device`` link on every cover entity dangles, because
        ``via_device`` alone does not create a device in HA's registry.
        """
        bridges = [
            p for p in ha_payloads if p["config"]["object_id"] == BRIDGE_OBJECT_ID
        ]
        assert len(bridges) == 1
        config = bridges[0]["config"]
        assert bridges[0]["topic"] == (
            "homeassistant/binary_sensor/velux2mqtt/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"
        assert config["device"]["identifiers"] == ["cosalette_velux2mqtt"]


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify HA-discovery state_topics match runtime-published topics."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]], harness_no_homing: AppHarness
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        Runs the real ``cover_device`` registration (2 covers, matching
        ``.env.schema``) via the integration-test ``harness_no_homing``
        (``FakeGpio`` substituted for real GPIO) and cross-checks each
        HA-discovery payload's ``state_topic`` against the topics actually
        published at runtime. A state_topic with no matching runtime publish
        would ship a phantom HA entity — exactly the regression that shipped
        in production before 's fix (PR #201), which this test guards
        against with runtime ground truth instead of a documentation-derived
        regex .

        The check itself is the framework helper ``assert_discovery_topics_published``
        (adopted per monorepo ADR-004 fed the CLI-generated payloads
        wrapped as ``SimpleNamespace`` objects (duck-typed;
        ``assert_discovery_topics_published`` only accesses
        ``.config.get('state_topic')``).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_app_briefly(harness_no_homing)

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(harness_no_homing, payloads)
