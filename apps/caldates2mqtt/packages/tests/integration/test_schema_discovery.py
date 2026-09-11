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

The same sensor carries the event list as HA attributes (cap-6hw). The comment
above ``_EVENT_COUNT_SENSOR`` in :mod:`caldates2mqtt.main` explains why.

At runtime ``app.discovery()`` publishes those entities from the live registry
(ADR-004, cap-2qg). The CLI payloads here are cross-checked against topics the
running app actually publishes (cap-gsd), not against f-strings rebuilt from the
same schema.

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
- Cross-check: every state_topic and json_attributes_topic is verified against
  topics the running app (FakeCalDavReader) actually publishes
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, assert_discovery_topics_published

from caldates2mqtt.adapters.fake import FakeCalDavReader
from ha_discovery import (
    BRIDGE_OBJECT_ID,
    configs_by_object_id,
    entities_without_bridge,
    parse_ha_discovery,
    run_ha_discovery,
)

from .conftest import TOPIC_PREFIX, calendar_config, make_harness, run_app_briefly

# packages/tests/integration/<file> → app root is parents[3]
APP_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = APP_ROOT / "docs" / "schema.yaml"
CALENDARS = ("birthday", "garbage")  # keys configured in .env.schema
_DISCOVERY_WAIT_TIMEOUT = 3.0


def _expected_config_topics(calendars: tuple[str, ...]) -> set[str]:
    """Return retained discovery config topics for calendars plus the bridge."""
    topics = {
        f"homeassistant/sensor/{TOPIC_PREFIX}/{calendar}_events/config"
        for calendar in calendars
    }
    topics.add(f"homeassistant/binary_sensor/{TOPIC_PREFIX}/bridge/config")
    return topics


def _expected_publishes(
    calendars: tuple[str, ...], *, include_states: bool = False
) -> dict[str, int]:
    """Return publication counts needed to observe a complete harness startup."""
    topics = _expected_config_topics(calendars)
    if include_states:
        topics.update(f"{TOPIC_PREFIX}/{calendar}/state" for calendar in calendars)
    return dict.fromkeys(topics, 1)


def _config_payload(harness: AppHarness, topic: str) -> dict[str, Any]:
    """Parse the discovery config payload published to *topic*."""
    payload = next(
        payload
        for published_topic, payload, *_ in harness.mqtt.published
        if published_topic == topic
    )
    return json.loads(payload)


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


@pytest.fixture
def schema_harness(fake_reader: FakeCalDavReader) -> AppHarness:
    """Harness over the ``.env.schema`` calendars, so runtime topics line up."""
    return make_harness(fake_reader, [calendar_config(c) for c in CALENDARS])


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
        serves every calendar. :class:`TestStateTopicsAreReal` checks the
        topic against what the app really publishes.

        Every field the composite declares is asserted, not a sample of them:
        ``name`` and ``icon`` are supplied by this app and would otherwise
        change unnoticed, and ``state_class`` is what lets Home Assistant keep
        long-term statistics for the count.

        Technique: Specification-based — the composite must produce one entity
        per real channel.
        """
        config = configs_by_id[f"{calendar}_events"]
        assert config["name"] == "Events"
        assert config["icon"] == "mdi:calendar"
        assert config["unique_id"] == f"cosalette_caldates2mqtt_{calendar}_events"
        assert config["value_template"] == "{{ value_json.events | length }}"
        assert config["unit_of_measurement"] == "events"
        assert config["state_class"] == "measurement"

    @pytest.mark.parametrize("calendar", CALENDARS)
    def test_event_list_rides_as_attributes_on_the_calendars_own_topic(
        self, configs_by_id: dict[str, dict[str, Any]], calendar: str
    ) -> None:
        """Each sensor carries its own calendar's event list as HA attributes.

        The composite declares only the template. The topic comes from the
        cosalette default (ADR-075); under 0.9.4 it was absent and the
        attributes never populated, so the topic is asserted too: it must be
        the sensor's own state topic. :class:`TestStateTopicsAreReal` checks
        that the app really publishes it.

        Technique: Specification-based — the attributes contract, pinned per
        calendar so a topic that stops resolving per channel fails.
        """
        config = configs_by_id[f"{calendar}_events"]
        assert (
            config["json_attributes_template"]
            == "{{ {'events': value_json.events} | tojson }}"
        )
        assert config["json_attributes_topic"] == config["state_topic"]

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

        Revisited for runtime discovery (cap-2qg): cosalette 0.9.6 still skips
        array-item annotations, so this guard is unchanged. Should upstream
        start deriving entities from them, the golden sets here and in
        :class:`TestRuntimeDiscoveryPublication` fail first.

        Technique: Error Guessing — asserts the diagnostic survives the fix,
        so a regression to silence is caught.
        """
        stderr = ha_discovery_run.stderr
        assert "array-item properties" in stderr
        assert "birthdayState" in stderr
        assert "garbageState" in stderr


@pytest.mark.integration
class TestRuntimeDiscoveryPublication:
    """app.discovery() publishes retained HA config topics on connect (cap-2qg)."""

    async def test_publishes_one_retained_config_per_calendar_plus_bridge(
        self, schema_harness: AppHarness
    ) -> None:
        """Exactly one retained sensor config per calendar, plus the bridge.

        Technique: Golden set — ADR-059 runtime publication against the live
        registry; a dropped or leaked entity fails, as does a non-retained one.
        """
        expected = _expected_config_topics(CALENDARS)
        await run_app_briefly(
            schema_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(CALENDARS),
        )

        retained = {t: r for t, _p, r, _q in schema_harness.mqtt.published}
        discovery = {t for t in retained if t.startswith("homeassistant/")}
        assert discovery == expected
        assert all(retained[t] for t in discovery)

    async def test_runtime_config_payloads_match_cli_topic_and_attribute_contracts(
        self,
        configs_by_id: dict[str, dict[str, Any]],
        schema_harness: AppHarness,
    ) -> None:
        """Runtime configs preserve each CLI config's state and attribute contract.

        Technique: Cross-check -- independently generated CLI configs and live
        registry configs must agree on the state topic, attributes topic, and
        attributes template for every calendar.
        """
        expected = _expected_config_topics(CALENDARS)
        await run_app_briefly(
            schema_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(CALENDARS),
        )

        for calendar in CALENDARS:
            topic = f"homeassistant/sensor/{TOPIC_PREFIX}/{calendar}_events/config"
            runtime_config = _config_payload(schema_harness, topic)
            cli_config = configs_by_id[f"{calendar}_events"]
            assert runtime_config["state_topic"] == cli_config["state_topic"]
            assert (
                runtime_config["json_attributes_topic"]
                == cli_config["json_attributes_topic"]
            )
            assert (
                runtime_config["json_attributes_template"]
                == cli_config["json_attributes_template"]
            )

    async def test_removes_retained_config_for_calendar_removed_after_restart(
        self, fake_reader: FakeCalDavReader
    ) -> None:
        """A restart clears the stale retained config after a calendar is removed.

        Technique: State Transition Testing -- two calendars on the first run,
        then one calendar on the same store, must emit one retained clear for
        the removed calendar's old config topic.
        """
        store = MemoryStore()
        first_harness = make_harness(
            fake_reader,
            [calendar_config(calendar) for calendar in CALENDARS],
            store=store,
        )
        await run_app_briefly(
            first_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(CALENDARS),
        )

        remaining = ("birthday",)
        restarted_harness = make_harness(
            fake_reader,
            [calendar_config(calendar) for calendar in remaining],
            store=store,
        )
        await run_app_briefly(
            restarted_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(remaining),
        )

        removed_topic = f"homeassistant/sensor/{TOPIC_PREFIX}/garbage_events/config"
        removed_messages = restarted_harness.mqtt.get_messages_for(removed_topic)
        assert removed_messages == [("", True, 1)]


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Verify discovery topics match runtime-published topics (cap-gsd)."""

    async def test_state_topics_match_actual_runtime_publishes(
        self, ha_payloads: list[dict[str, Any]], schema_harness: AppHarness
    ) -> None:
        """Every discovery state_topic is a topic the running app publishes.

        The check is the framework helper ``assert_discovery_topics_published``
        (ADR-004 / cap-6y0), fed the CLI payloads as ``SimpleNamespace``
        objects (it only reads ``.config.get('state_topic')``).

        Technique: Cross-check — the schema-derived expectation is validated
        against runtime ground truth, not a string derived from the same schema.
        """
        await run_app_briefly(
            schema_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(CALENDARS, include_states=True),
        )

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(schema_harness, payloads)

    async def test_attribute_topics_match_actual_runtime_publishes(
        self, entity_payloads: list[dict[str, Any]], schema_harness: AppHarness
    ) -> None:
        """Every json_attributes_topic is a topic the running app publishes.

        A wrong address would give Home Assistant an attributes topic nobody
        publishes to. The helper reads only ``state_topic``, so each
        ``json_attributes_topic`` is passed under that key.

        Technique: Cross-check — as above, for the second generated topic.
        """
        await run_app_briefly(
            schema_harness,
            wait=_DISCOVERY_WAIT_TIMEOUT,
            expected_publishes=_expected_publishes(CALENDARS, include_states=True),
        )

        attribute_topics = [
            p["config"]["json_attributes_topic"] for p in entity_payloads
        ]
        payloads = [
            SimpleNamespace(config={"state_topic": t}) for t in attribute_topics
        ]
        assert_discovery_topics_published(schema_harness, payloads)
