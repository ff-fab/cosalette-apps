"""Integration tests for docs/schema.yaml — Home Assistant MQTT discovery generation.

``app.telemetry`` is registered with a callable ``name=`` (``_calendar_map`` in
:mod:`caldates2mqtt.main`, keyed off user-configured ``settings.calendars``). A
plain ``cosalette schema init``/``check`` would collapse every real per-calendar
device into a single channel named after the Python handler's qualname
(``calendar``), which is why ``task caldates2mqtt:schema:generate`` instead runs
``cosalette schema dump --resolve-settings`` (ADR-051) against the checked-in
``.env.schema`` profile before writing ``docs/schema.yaml`` — expanding the
NameSpec into real per-calendar channels (``birthdayState``, ``garbageState``,
per ``.env.schema``). This resolves the same qualname-collapse issue fixed for
velux2mqtt (cap-hze), verified below by asserting the real channel names appear.

HA discovery (``task caldates2mqtt:schema:ha-discovery``) emits one event-count
sensor per calendar, plus the ADR-058 app bridge. It reaches that from the
channel-level ``ha_entities()`` composite on ``CalendarState``, not from the
per-event annotations: ``CalendarState``'s only property is ``events``, an array
of objects, and an array of objects has no single value an HA sensor could hold.
The ``consumer()`` annotations on ``CalendarEvent`` (see :mod:`caldates2mqtt.main`)
therefore stay inert and still warn on stderr. The composite is the supported
answer to that (cosalette ADR-057), and it is what satisfies the per-channel
discovery gate cosalette 0.9.4 introduced.

The event *list* rides on the same sensor as HA attributes (cap-6hw). The
composite sets ``json_attributes_template``; cosalette 0.9.5 then defaults
``json_attributes_topic`` to the channel's own resolved state topic (ADR-075),
so one model-level spec names each calendar's own topic. The assertions below
pin both, because a regression to the 0.9.4 behaviour drops the topic key and
leaves the attributes silently unpopulated in Home Assistant.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must expose real per-calendar
  channel names, not the qualname placeholder
- Specification-based: the channel-level ha_entities() composite yields one
  event-count sensor per calendar, each carrying its own event list as
  attributes; the array-item annotations stay inert and
  still warn, but the composite satisfies the per-channel *Home Assistant* gate
  (cosalette ADR-073). It does not satisfy the openHAB generator, which ignores
  ha_entities composites — ``task caldates2mqtt:schema:openhab`` still exits 1,
  as it did before the composite existed.
- Golden set: the exact object_id set, so both a dropped entity and a leaked
  one fail
- Parametrize: per-calendar assertions name the failing calendar
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from ha_discovery import (
    BRIDGE_OBJECT_ID,
    configs_by_object_id,
    entities_without_bridge,
    parse_ha_discovery,
    run_ha_discovery,
)

# packages/tests/integration/<file> → app root is parents[3]
APP_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = APP_ROOT / "docs" / "schema.yaml"
CALENDARS = ("birthday", "garbage")  # keys configured in .env.schema


@pytest.fixture(scope="module")
def schema_channels() -> dict[str, Any]:
    """Return the ``channels`` mapping from the committed docs/schema.yaml."""
    doc = yaml.safe_load(SCHEMA_PATH.read_text())
    return doc["channels"]


@pytest.fixture(scope="module")
def ha_discovery_run() -> subprocess.CompletedProcess[str]:
    """Run the schema ha-discovery CLI once and return the completed process.

    Kept separate from :func:`ha_payloads` because the warning assertions
    below read ``.stderr`` off the same run.
    """
    return run_ha_discovery(SCHEMA_PATH)


@pytest.fixture(scope="module")
def ha_payloads(
    ha_discovery_run: subprocess.CompletedProcess[str],
) -> list[dict[str, Any]]:
    """All discovery payloads the CLI emitted, bridge included."""
    return parse_ha_discovery(ha_discovery_run)


@pytest.fixture(scope="module")
def entity_payloads(ha_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discovery payloads for the app's own entities, without the bridge."""
    return entities_without_bridge(ha_payloads)


@pytest.fixture(scope="module")
def configs_by_id(entity_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    return configs_by_object_id(entity_payloads)


@pytest.mark.integration
class TestResolvedSchemaChannels:
    """Verify schema:generate resolved real per-calendar channels."""

    def test_real_calendar_channels_present(
        self, schema_channels: dict[str, Any]
    ) -> None:
        """docs/schema.yaml exposes real per-calendar channels from .env.schema.

        Guards against a regression back to the qualname-collapse placeholder
        (``calendarState``, address ``caldates2mqtt/calendar/state``) that a
        plain ``cosalette schema init``/``check`` would produce.

        Technique: Specification-based — resolved channel names must match
        the calendar keys configured in ``.env.schema``.
        """
        assert "calendarState" not in schema_channels
        assert set(schema_channels) == {"birthdayState", "garbageState"}
        assert (
            schema_channels["birthdayState"]["address"]
            == "caldates2mqtt/birthday/state"
        )
        assert (
            schema_channels["garbageState"]["address"] == "caldates2mqtt/garbage/state"
        )


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify the channel-level composite yields one sensor per calendar."""

    def test_emits_exactly_one_event_count_sensor_per_calendar(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The app's own entity set is exactly one sensor per calendar.

        Technique: Golden set — a superset means an entity leaked, a subset
        means the composite stopped resolving for some calendar.
        """
        assert set(configs_by_id) == {f"{c}_events" for c in CALENDARS}

    @pytest.mark.parametrize("calendar", CALENDARS)
    def test_event_count_sensor_config(
        self, configs_by_id: dict[str, dict[str, Any]], calendar: str
    ) -> None:
        """Each calendar's sensor carries the full composite spec.

        ``CalendarState`` carries an ``ha_entities()`` composite (cosalette
        ADR-057) — the supported path for a payload whose only property is an
        array of objects. cosalette resolves each per-calendar ``state_topic``
        and ``unique_id`` from the channel address, so one model-level spec
        serves every calendar.

        Every field the composite declares is asserted, not a sample of them:
        ``name`` and ``icon`` are supplied by this app and would otherwise
        change unnoticed, and ``state_class`` is what lets Home Assistant keep
        long-term statistics for the count.

        Technique: Specification-based — the composite must produce one entity
        per real channel, keyed to that channel's own topic.
        """
        config = configs_by_id[f"{calendar}_events"]
        assert config["name"] == "Events"
        assert config["icon"] == "mdi:calendar"
        assert config["unique_id"] == f"cosalette_caldates2mqtt_{calendar}_events"
        assert config["state_topic"] == f"caldates2mqtt/{calendar}/state"
        assert config["value_template"] == "{{ value_json.events | length }}"
        assert config["unit_of_measurement"] == "events"
        assert config["state_class"] == "measurement"

    @pytest.mark.parametrize("calendar", CALENDARS)
    def test_event_list_rides_as_attributes_on_the_calendars_own_topic(
        self, configs_by_id: dict[str, dict[str, Any]], calendar: str
    ) -> None:
        """Each sensor carries its own calendar's event list as HA attributes.

        The composite declares only ``json_attributes_template``. cosalette
        0.9.5 defaults ``json_attributes_topic`` to the channel's own resolved
        state topic (ADR-075), which is what lets one model-level spec serve
        every callable-named calendar. Under 0.9.4 the key was absent and the
        attributes never populated, so this asserts the topic as well as the
        template.

        The template must yield a JSON object. ``value_json | tojson`` gives
        ``{"events": [...]}``; ``value_json.events | tojson`` would give a bare
        array, which Home Assistant rejects.

        Technique: Specification-based — the attributes contract, pinned per
        calendar so a topic that stops resolving per channel fails.
        """
        config = configs_by_id[f"{calendar}_events"]
        assert config["json_attributes_template"] == "{{ value_json | tojson }}"
        assert config["json_attributes_topic"] == f"caldates2mqtt/{calendar}/state"

    @pytest.mark.parametrize("calendar", CALENDARS)
    def test_event_count_sensor_device_grouping(
        self, configs_by_id: dict[str, dict[str, Any]], calendar: str
    ) -> None:
        """Each sensor sits on its own calendar device, linked to the bridge.

        cosalette 0.6.2 (ADR-058) models each resolved device as its own HA
        device linked to the app bridge via ``via_device``.

        Technique: Specification-based — HA device grouping contract.
        """
        device = configs_by_id[f"{calendar}_events"]["device"]
        assert device["identifiers"] == [f"cosalette_caldates2mqtt_{calendar}"]
        assert device["via_device"] == "cosalette_caldates2mqtt"

    def test_emits_app_bridge_entity(self, ha_payloads: list[dict[str, Any]]) -> None:
        """A single diagnostic bridge entity materialises the app device.

        Technique: Specification-based — ADR-058 bridge contract. Without it
        the ``via_device`` link on every real entity dangles, because
        ``via_device`` alone does not create a device in HA's registry.
        """
        bridges = [
            p["config"]
            for p in ha_payloads
            if p["config"]["object_id"] == BRIDGE_OBJECT_ID
        ]
        assert len(bridges) == 1
        bridge = bridges[0]
        assert bridge["device_class"] == "connectivity"
        assert bridge["entity_category"] == "diagnostic"
        assert bridge["device"]["identifiers"] == ["cosalette_caldates2mqtt"]

    def test_still_reports_the_array_item_annotations_it_skips(
        self, ha_discovery_run: subprocess.CompletedProcess[str]
    ) -> None:
        """The CLI names the skipped array-item annotations but now exits 0.

        The ``consumer()`` annotations on ``CalendarEvent`` remain, and
        cosalette still skips them: an array item has no single value. The
        warning stays because those annotations are genuinely inert for Home
        Assistant. The exit code is 0 because the channel-level composite
        satisfies the per-channel discovery gate (ADR-073).

        Technique: Error Guessing — asserts the diagnostic survives the fix,
        so a regression to silence is caught.
        """
        stderr = ha_discovery_run.stderr
        assert "array-item properties" in stderr
        assert "birthdayState" in stderr
        assert "garbageState" in stderr
