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

The event *list* itself remains off Home Assistant. Carrying it would need
``json_attributes_topic``, which 0.9.4 neither emits nor can resolve per
instance from a model-level spec shared by every calendar (cap-wxg).

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must expose real per-calendar
  channel names, not the qualname placeholder
- Specification-based: the channel-level ha_entities() composite yields one
  event-count sensor per calendar; the array-item annotations stay inert and
  still warn, but the composite satisfies the per-channel *Home Assistant* gate
  (cosalette ADR-073). It does not satisfy the openHAB generator, which ignores
  ha_entities composites — ``task caldates2mqtt:schema:openhab`` still exits 1,
  as it did before the composite existed.
- Golden set: the exact object_id set, so both a dropped entity and a leaked
  one fail
- Parametrize: per-calendar assertions name the failing calendar
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

# packages/tests/integration/<file> → app root is parents[3]
APP_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = APP_ROOT / "docs" / "schema.yaml"
BRIDGE_OBJECT_ID = "bridge"  # ADR-058 synthetic bridge sentinel
CALENDARS = ("birthday", "garbage")  # keys configured in .env.schema


@pytest.fixture(scope="module")
def schema_channels() -> dict[str, Any]:
    """Return the ``channels`` mapping from the committed docs/schema.yaml."""
    doc = yaml.safe_load(SCHEMA_PATH.read_text())
    return doc["channels"]


@pytest.fixture(scope="module")
def ha_discovery_run() -> subprocess.CompletedProcess[str]:
    """Run the schema ha-discovery CLI once and return the completed process.

    ``check=False`` so a non-zero exit surfaces as one named assertion failure
    with the CLI's stderr attached. Under ``check=True`` the raised
    ``CalledProcessError`` renders only "returned non-zero exit status 1" and
    the sentence naming the offending channels is lost in the unread
    ``.stderr`` — and because this fixture is module-scoped, every test in the
    module would ERROR instead of one FAILing with the reason.
    """
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=False,
        env={
            k: v
            for k, v in os.environ.items()
            if k not in {"PYTHONSTARTUP", "PYTHONHOME"}
        },
    )
    assert result.returncode == 0, (
        f"ha-discovery exited {result.returncode}:\n{result.stderr}"
    )
    return result


@pytest.fixture(scope="module")
def ha_payloads(
    ha_discovery_run: subprocess.CompletedProcess[str],
) -> list[dict[str, Any]]:
    """All discovery payloads the CLI emitted, bridge included."""
    payloads: list[dict[str, Any]] = json.loads(ha_discovery_run.stdout)
    return payloads


@pytest.fixture(scope="module")
def entity_payloads(ha_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discovery payloads for the app's own entities, without the bridge.

    cosalette 0.6.2 (ADR-058) emits one synthetic per-app ``bridge``
    binary_sensor so Home Assistant materialises the device every real entity
    links to via ``via_device``. It is framework plumbing rather than a
    caldates2mqtt datapoint, so it is asserted in its own test and kept out of
    the golden entity set here — the convention every sibling app follows.
    """
    return [p for p in ha_payloads if p["config"]["object_id"] != BRIDGE_OBJECT_ID]


@pytest.fixture(scope="module")
def configs_by_id(entity_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    return {p["config"]["object_id"]: p["config"] for p in entity_payloads}


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
