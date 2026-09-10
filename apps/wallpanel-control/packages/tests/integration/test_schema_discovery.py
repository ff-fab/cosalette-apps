"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

Guards the channel-level composite in the AsyncAPI schema: regenerating the
schema with ``cosalette schema init`` (or
``task wallpanel-control:schema:generate``) strips the
``x-cosalette-ha-discovery`` composite, which would silently break HA discovery.
These tests fail loudly if that happens.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the composite must yield one HA light for the display
- Cross-check (cap-5f8): every state_topic is verified against topics the
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

from .conftest import DISPLAY_SET, run_with_commands

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
    """Verify the schema produces one composite HA light for the display."""

    def test_display_collapses_to_one_light(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """The display's two channels surface as a single ``light`` entity.

        cosalette 0.9.5's channel-level composite (ADR-057) merges the ``/set``
        and ``/state`` channels into one entity when the same ``ha_entities()``
        spec rides on both ``DisplayCommand`` and ``DisplayState``. That replaces
        the four scalar entities (two sensors + a select + a number) the
        per-field ``consumer()`` annotations used to emit (cap-c9v).

        Technique: Specification-based — system/action is command-ack only and
        carries no consumer metadata, so it produces no HA entity either.
        """
        assert [p["config"]["object_id"] for p in entity_payloads] == [
            "display_display"
        ]
        light = entity_payloads[0]
        assert light["topic"] == (
            "homeassistant/light/wallpanel_control/display_display/config"
        )
        assert light["config"]["unique_id"] == (
            "cosalette_wallpanel_control_display_display"
        )

    def test_display_light_template_config(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The light maps HA's vocabulary onto the app's wire payloads.

        The composite uses HA's ``template`` light schema so the MQTT contract
        stays unchanged: brightness is 1-100 on the wire but 0-255 in HA, and
        state is lower-case ``on``/``off``. The command templates publish to the
        ``/set`` channel; the state templates read the ``/state`` channel.

        Technique: Specification-based — locks the composite's read/write topics
        and template keys so a regression dropping the mapping fails loudly.
        """
        config = configs_by_id["display_display"]
        assert config["schema"] == "template"
        assert config["state_topic"] == "wallpanel-control/display/state"
        assert config["command_topic"] == "wallpanel-control/display/set"
        for key in (
            "command_on_template",
            "command_off_template",
            "state_template",
            "brightness_template",
        ):
            assert config.get(key), f"missing {key} on composite light"

    def test_payloads_grouped_under_per_device_ha_devices(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """The light sits on the per-device ``display`` HA device.

        cosalette 0.6.2 (ADR-058) models each resolved device as its own HA
        device linked to the app bridge via ``via_device``, replacing the
        single app-wide device earlier releases emitted.

        Technique: Specification-based — HA device grouping contract.
        """
        for payload in entity_payloads:
            assert payload["topic"].startswith("homeassistant/")
            assert "/wallpanel_control/" in payload["topic"]
            device = payload["config"]["device"]
            assert device["identifiers"] == ["cosalette_wallpanel_control_display"]
            assert device["via_device"] == "cosalette_wallpanel_control"

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
            "homeassistant/binary_sensor/wallpanel_control/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"
        assert config["device"]["identifiers"] == ["cosalette_wallpanel_control"]

    def test_writable_components_carry_a_command_topic(
        self, ha_payloads: list[dict[str, Any]]
    ) -> None:
        """No writable HA component is emitted without a command_topic.

        The display light is a writable component; without the composite's
        ``command_topic`` (sourced from the ``/set`` channel) Home Assistant
        would reject a light it cannot command.

        Technique: Error Guessing — anticipates the specific failure mode of a
        writable component with no way to write.
        """
        writable = {"number", "select", "switch", "text", "light", "climate", "cover"}
        for payload in ha_payloads:
            component = payload["topic"].split("/")[1]
            if component in writable:
                assert "command_topic" in payload["config"], (
                    f"{payload['topic']}: {component} is a writable component but "
                    "carries no command_topic"
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
        cross-checks each HA-discovery payload's ``state_topic`` against the
        topics actually published at runtime. A state_topic with no matching
        runtime publish would ship a phantom HA entity (cap-5f8).

        The check itself is the framework helper ``assert_discovery_topics_published``
        (adopted per monorepo ADR-004 / cap-6y0), fed the CLI-generated payloads
        wrapped as ``SimpleNamespace`` objects (duck-typed;
        ``assert_discovery_topics_published`` only accesses
        ``.config.get('state_topic')``).

        Technique: Cross-check — the schema-derived expectation
        (``ha_payloads``) is validated against runtime ground truth, not
        another string independently derived from the same schema.
        """
        await run_with_commands(harness, [(DISPLAY_SET, {"state": "on"})])

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(harness, payloads)


@pytest.mark.integration
class TestDiscoveryOptOut:
    """Lock which channels are opted out of consumer discovery (ADR-073).

    ``cosalette schema check`` compares registered device names only; it never
    reads ``x-cosalette-discoverable``. Without these assertions a flag flip is
    invisible to CI in either direction — a lost sensor surfaces only as a
    golden-set mismatch, and a lost opt-out not at all.

    Test Techniques Used:
    - Specification-based: assert the committed schema against the documented
      per-channel intent rather than against regenerated output.
    - Golden set: the exact opted-out channel set, so both a stripped flag and
      a leaked one fail.
    """

    @pytest.fixture(scope="class")
    def schema_channels(self) -> dict[str, Any]:
        """Parse the committed schema and return its channels mapping."""
        import yaml

        document = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
        channels: dict[str, Any] = document["channels"]
        return channels

    def test_opted_out_channels_are_exactly_the_documented_set(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """Every opt-out is deliberate and documented.

        Reasons, one per channel:
        - ``systemActionCommand``: fire-and-forget power verbs
          (wake / suspend / hibernate).
        - ``systemActionState``: command acknowledgement, not a datapoint.
        """
        opted_out = {
            name
            for name, channel in schema_channels.items()
            if channel.get("x-cosalette-discoverable") is False
        }
        assert opted_out == {
            "systemActionCommand",
            "systemActionState",
        }

    def test_remaining_channels_stay_discoverable(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """No channel outside that set carries the flag.

        Technique: Error Guessing — the specific failure mode is an opt-out
        leaking across a channel merge onto a channel that owns real entities.
        """
        for name, channel in schema_channels.items():
            if name in {
                "systemActionCommand",
                "systemActionState",
            }:
                continue
            assert channel.get("x-cosalette-discoverable") is not False, (
                f"{name} was opted out of discovery without a recorded reason"
            )
