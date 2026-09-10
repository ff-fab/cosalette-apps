"""Integration tests for Home Assistant MQTT discovery in jeelink2mqtt.

Covers both halves of the discovery adoption:

* **cap-egy** — ``SensorStateModel``'s ``temperature``/``humidity``/
  ``low_battery`` fields carry ``x-cosalette-consumer`` metadata (see
  :mod:`jeelink2mqtt.models`), and ``docs/schema.yaml`` is regenerated
  from the settings-resolved registry (``task jeelink2mqtt:schema:generate``,
  ADR-051). ``TestHaDiscoveryGeneration`` runs the offline
  ``cosalette schema ha-discovery`` CLI against that checked-in artifact
  and pins the entities it must emit.
* **cap-hpa** — :mod:`jeelink2mqtt.main` calls ``app.discovery()`` (ADR-059),
  so retained ``homeassistant/<component>/.../config`` payloads are published
  on the first MQTT connect. ``TestRuntimeDiscoveryPublication`` runs the
  real wiring through :class:`~cosalette.testing.AppHarness` and asserts the
  payloads land. ``TestStateTopicsAreReal`` cross-checks every generated
  ``state_topic`` against a topic the per-sensor device actually publishes,
  via the framework helper ``assert_discovery_topics_published`` (ADR-004 /
  cap-6y0).

``sensor_entity`` registers with a callable ``name=`` NameSpec keyed off
``settings.sensors``; the ``.env.schema`` profile the schema is generated
from configures two sensors (``office``, ``outdoor``), so both the CLI
output and the runtime registry expand to six per-field entities plus the
ADR-058 bridge.

Note: Lives in integration/ because it spawns a subprocess and reads from
the filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must yield the documented HA entities
- Equivalence Partitioning: sensor (temperature/humidity) vs binary_sensor
  (low_battery); unannotated ``timestamp`` yields nothing
- Cross-check (cap-5f8): every discovery ``state_topic`` is verified against a
  topic the running device actually publishes, not a string re-derived from
  the same schema
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cosalette
import pytest
from cosalette import MockMqttClient
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, FakeClock, assert_discovery_topics_published

from ha_discovery import (
    BRIDGE_OBJECT_ID,
    configs_by_object_id,
    entities_without_bridge,
    load_ha_discovery_payloads,
)
from jeelink2mqtt import receiver as _receiver
from jeelink2mqtt.models import SensorReading, SensorStateModel
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import SharedState, build_shared_state
from tests.fixtures.async_utils import wait_for_condition

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"
TOPIC_PREFIX = "jeelink2mqtt"
SENSOR_NAMES = ("office", "outdoor")  # matches apps/jeelink2mqtt/.env.schema
# Runtime tests build settings dynamically, so they can exercise a multi-word
# sensor name that the checked-in ``.env.schema`` profile does not include.
# ``SensorConfigSettings.name`` permits underscores, and ``low_battery`` is
# itself an underscored field — this guards the object_id -> device mapping
# against any single-token assumption creeping back in.
RUNTIME_SENSOR_NAMES = ("office", "living_room")
# The annotated fields on ``SensorStateModel`` and the HA component each maps to.
# Declared once so the field/component contract is not restated per test.
FIELD_COMPONENTS = (
    ("temperature", "sensor"),
    ("humidity", "sensor"),
    ("low_battery", "binary_sensor"),
)
FIELDS = tuple(field for field, _ in FIELD_COMPONENTS)
_WAIT_TIMEOUT = 3.0


def _expected_config_topics(names: tuple[str, ...]) -> set[str]:
    """The retained discovery ``config`` topics for *names* plus the bridge."""
    topics = {
        f"homeassistant/{component}/{TOPIC_PREFIX}/{sensor}_{field}/config"
        for sensor in names
        for field, component in FIELD_COMPONENTS
    }
    topics.add(f"homeassistant/binary_sensor/{TOPIC_PREFIX}/bridge/config")
    return topics


# ---------------------------------------------------------------------------
# cap-egy — offline HA discovery generation from docs/schema.yaml
# ---------------------------------------------------------------------------


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
    """Verify the enriched schema produces valid HA MQTT discovery payloads."""

    def test_generates_one_entity_per_annotated_field_per_sensor(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """Three annotated fields × two configured sensors → six entities.

        ``timestamp`` carries no ``consumer()`` block, so it yields nothing.

        Technique: Specification-based — count matches annotated properties.
        """
        expected = {f"{sensor}_{field}" for sensor in SENSOR_NAMES for field in FIELDS}
        object_ids = {p["config"]["object_id"] for p in entity_payloads}
        assert object_ids == expected
        unique_ids = [p["config"]["unique_id"] for p in entity_payloads]
        assert all(unique_ids), "every entity must carry a non-empty unique_id"
        assert len(set(unique_ids)) == len(unique_ids), (
            "unique_ids must be collision-free — HA relies on them to dedupe entities"
        )

    def test_payloads_grouped_under_per_sensor_device(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """Every entity is grouped under its sensor's HA device (ADR-058).

        Technique: Specification-based — HA device grouping contract. The
        expected device identity is iterated forward from the known sensor
        names rather than reverse-parsed from ``object_id`` (which cannot
        round-trip a multi-word name past the underscored ``low_battery`` field).
        """
        for sensor in SENSOR_NAMES:
            for field in FIELDS:
                device = configs_by_id[f"{sensor}_{field}"]["device"]
                assert device["identifiers"] == [f"cosalette_{TOPIC_PREFIX}_{sensor}"]
                assert device["via_device"] == f"cosalette_{TOPIC_PREFIX}"

    def test_emits_app_bridge_entity(self, ha_payloads: list[dict[str, Any]]) -> None:
        """A single diagnostic bridge entity materialises the app device.

        Technique: Specification-based — ADR-058 bridge contract.
        """
        bridges = [
            p for p in ha_payloads if p["config"]["object_id"] == BRIDGE_OBJECT_ID
        ]
        assert len(bridges) == 1
        config = bridges[0]["config"]
        assert bridges[0]["topic"] == (
            f"homeassistant/binary_sensor/{TOPIC_PREFIX}/bridge/config"
        )
        assert config["device_class"] == "connectivity"
        assert config["entity_category"] == "diagnostic"

    @pytest.mark.parametrize(
        "field, component, expected",
        [
            (
                "temperature",
                "sensor",
                {
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.temperature }}",
                },
            ),
            (
                "humidity",
                "sensor",
                {
                    "device_class": "humidity",
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "value_template": "{{ value_json.humidity }}",
                },
            ),
            (
                "low_battery",
                "binary_sensor",
                {
                    "device_class": "battery",
                    "value_template": "{{ 'ON' if value_json.low_battery else 'OFF' }}",
                },
            ),
        ],
    )
    def test_field_config_matches_consumer_annotations(
        self,
        entity_payloads: list[dict[str, Any]],
        configs_by_id: dict[str, dict[str, Any]],
        field: str,
        component: str,
        expected: dict[str, Any],
    ) -> None:
        """Each field's HA config carries the metadata declared on the model.

        Technique: Equivalence Partitioning — measurement sensors (device_class,
        unit, state_class) vs the boolean binary_sensor (device_class + a
        value_template mapping JSON true/false to HA's ON/OFF payloads).
        """
        for sensor in SENSOR_NAMES:
            config = configs_by_id[f"{sensor}_{field}"]
            assert config["state_topic"] == f"{TOPIC_PREFIX}/{sensor}/state"
            for key, value in expected.items():
                assert config.get(key) == value, (
                    f"{sensor}_{field}: expected {key}={value!r}, "
                    f"got {config.get(key)!r}"
                )
            payload = next(
                p
                for p in entity_payloads
                if p["config"]["object_id"] == f"{sensor}_{field}"
            )
            assert payload["topic"].startswith(f"homeassistant/{component}/")


# ---------------------------------------------------------------------------
# cap-hpa — runtime discovery publication via app.discovery()
# ---------------------------------------------------------------------------


def _make_settings(names: tuple[str, ...] = SENSOR_NAMES) -> Jeelink2MqttSettings:
    """Settings for the given sensor *names* (defaults to the schema profile)."""
    return Jeelink2MqttSettings(
        sensors=[SensorConfigSettings(name=name) for name in names],
        serial_port="/dev/null",
        _env_file=None,  # type: ignore[call-arg]
    )


def _build_discovery_app(captured: dict[str, Any]) -> cosalette.App:
    """Mirror ``jeelink2mqtt.main``'s per-sensor wiring with ``app.discovery()``.

    Only the pieces discovery reads are registered: the per-sensor
    ``sensor_entity`` device (callable NameSpec) and its ``SharedState``
    factory, which records the built state into *captured* so a test can
    drive the per-sensor publish path directly. Backed by a ``MemoryStore``
    so the test touches no disk.
    """
    app = cosalette.App(
        name=TOPIC_PREFIX,
        version="0.0.0",
        settings_class=Jeelink2MqttSettings,
        store=MemoryStore(),
    )
    app.discovery()

    @app.state
    def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
        state = build_shared_state(settings)
        captured["state"] = state
        return state

    @app.device(
        name=lambda s: {sc.name: sc for sc in s.sensors},
        summary="Per-sensor state publisher",
        state_model=SensorStateModel,
        triggerable="local",
    )
    async def sensor_entity(
        ctx: cosalette.DeviceContext,
        config: SensorConfigSettings,
        settings: Jeelink2MqttSettings,
        state: SharedState,
        trigger: cosalette.DeviceTrigger,
    ) -> AsyncIterator[None]:
        while not ctx.shutdown_requested:
            await trigger.wait(timeout=3600.0)
            yield

    return app


@pytest.fixture
def captured() -> dict[str, Any]:
    """Receives the ``SharedState`` the app's state factory builds."""
    return {}


@pytest.fixture
def harness(captured: dict[str, Any]) -> AppHarness:
    """AppHarness over the discovery-enabled app, using the schema sensor names.

    Shared by the cross-check test, whose ground-truth publishes must line up
    with the offline ``ha_payloads`` generated from the ``.env.schema`` profile.
    """
    return AppHarness(
        app=_build_discovery_app(captured),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=_make_settings(SENSOR_NAMES),
        shutdown_event=asyncio.Event(),
    )


@pytest.fixture
def runtime_harness() -> AppHarness:
    """AppHarness whose sensor set includes a multi-word name (``living_room``).

    The runtime path builds its registry from settings rather than the
    checked-in schema, so it can exercise an underscored sensor name and lock
    in the object_id -> device mapping for realistic configurations.
    """
    return AppHarness(
        app=_build_discovery_app({}),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=_make_settings(RUNTIME_SENSOR_NAMES),
        shutdown_event=asyncio.Event(),
    )


async def _run_until_discovery_published(
    harness: AppHarness, expected: set[str]
) -> None:
    """Start the harness, wait until *all* expected config topics land, shut down.

    Waiting for the complete set — not merely the first ``homeassistant/`` topic
    — keeps the shutdown from racing ahead of a partial publish, so callers can
    assert against the full topic set deterministically.
    """
    task = asyncio.create_task(harness.run())
    try:
        await wait_for_condition(
            lambda: expected <= {topic for topic, *_ in harness.mqtt.published},
            timeout=_WAIT_TIMEOUT,
            description="app.discovery() to publish all config topics",
        )
    finally:
        harness.shutdown_event.set()
        await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)


@pytest.mark.integration
class TestRuntimeDiscoveryPublication:
    """app.discovery() publishes retained HA config topics on first connect."""

    async def test_publishes_retained_config_topic_per_entity(
        self, runtime_harness: AppHarness
    ) -> None:
        """One retained config topic per per-field entity, plus the bridge.

        Exercises a multi-word sensor name (``living_room``) so the object_id ->
        topic mapping is verified for underscored names, not just single tokens.

        Technique: Specification-based — ADR-059 runtime publication contract,
        against the live registry rather than the checked-in schema.
        """
        expected = _expected_config_topics(RUNTIME_SENSOR_NAMES)
        await _run_until_discovery_published(runtime_harness, expected)

        published = {
            topic: retain
            for topic, _payload, retain, _qos in runtime_harness.mqtt.published
        }
        discovery = {topic for topic in published if topic.startswith("homeassistant/")}
        assert discovery == expected, "runtime discovery topics must match exactly"
        assert all(published[topic] for topic in expected), "config topics must retain"

    async def test_config_payload_targets_real_state_topic(
        self, runtime_harness: AppHarness
    ) -> None:
        """A published config points HA at the sensor's real state topic.

        ``living_room`` confirms the state topic is built from the full,
        underscored sensor name rather than a truncated token.

        Technique: Specification-based — the discovery payload is self-consistent
        with the app's own topic layout.
        """
        await _run_until_discovery_published(
            runtime_harness, _expected_config_topics(RUNTIME_SENSOR_NAMES)
        )

        topic = f"homeassistant/sensor/{TOPIC_PREFIX}/living_room_temperature/config"
        payload = next(p for t, p, *_ in runtime_harness.mqtt.published if t == topic)
        config = json.loads(payload)
        assert config["state_topic"] == f"{TOPIC_PREFIX}/living_room/state"
        assert config["value_template"] == "{{ value_json.temperature }}"


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Every discovery state_topic matches a topic a sensor device publishes."""

    async def test_state_topics_match_actual_runtime_publishes(
        self,
        harness: AppHarness,
        captured: dict[str, Any],
        ha_payloads: list[dict[str, Any]],
    ) -> None:
        """Cross-check the generated payloads against real publishes.

        Drives each per-sensor device's publish path directly (the stream that
        feeds it in production is suppressed by ``AppHarness.run`` — see
        ``test_event_driven_acceptance``), caching a calibrated reading and
        an assigned mapping so ``sensor_entity_tick`` publishes
        ``{prefix}/{sensor}/state``. ``assert_discovery_topics_published``
        (ADR-004 / cap-6y0) then fails if any discovery ``state_topic`` was
        never published.

        Technique: Cross-check — schema-derived expectation validated against
        runtime ground truth, not another string derived from the same schema.
        """
        task = asyncio.create_task(harness.run())
        try:
            await wait_for_condition(
                lambda: "state" in captured,
                timeout=_WAIT_TIMEOUT,
                description="the state factory to build SharedState",
            )
            state: SharedState = captured["state"]

            for sensor_id, name in enumerate(SENSOR_NAMES, start=1):
                state.registry.assign(name, sensor_id)
                state.record_calibrated_reading(
                    name,
                    SensorReading(
                        sensor_id=sensor_id,
                        temperature=21.5,
                        humidity=55,
                        low_battery=False,
                        timestamp=datetime.now(UTC),
                    ),
                )
                ctx = cosalette.DeviceContext(
                    name=name,
                    settings=harness.settings,
                    mqtt=harness.mqtt,
                    topic_prefix=TOPIC_PREFIX,
                    shutdown_event=harness.shutdown_event,
                    adapters={},
                    clock=harness.clock,
                    state_model=SensorStateModel,
                )
                await _receiver.sensor_entity_tick(
                    ctx, name, harness.settings, state, triggered=True
                )
        finally:
            harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)

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
        - ``mappingCommand``: operator control surface for administering the
          sensor-id map.
        - ``mappingState``: command acknowledgement, not a sensor reading.
        """
        opted_out = {
            name
            for name, channel in schema_channels.items()
            if channel.get("x-cosalette-discoverable") is False
        }
        assert opted_out == {
            "mappingCommand",
            "mappingState",
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
                "mappingCommand",
                "mappingState",
            }:
                continue
            assert channel.get("x-cosalette-discoverable") is not False, (
                f"{name} was opted out of discovery without a recorded reason"
            )
