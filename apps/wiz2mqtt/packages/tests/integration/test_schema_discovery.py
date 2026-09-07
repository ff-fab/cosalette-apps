"""Integration tests for Home Assistant MQTT discovery in wiz2mqtt (cap-10u.14).

Covers both halves of the consumer-integration adoption:

* **Offline generation** — :mod:`wiz2mqtt.models` declares the composite HA
  ``light``/``sensor``/``number`` entities via ``ha_entities`` on
  ``BulbStateModel`` / ``BulbSetCommand``, and ``docs/schema.yaml`` is
  regenerated from the settings-resolved registry
  (``task wiz2mqtt:schema:generate``). ``TestHaDiscoveryGeneration`` runs the
  offline ``cosalette schema ha-discovery`` CLI against that checked-in
  artifact and pins the entities it must emit — the ``light`` merging the
  ``/state`` and ``/set`` channels into one entity with both a ``state_topic``
  and a ``command_topic`` (cosalette ADR-057).
* **Runtime publication** — :mod:`wiz2mqtt.main` calls ``app.discovery()``
  (ADR-059), so retained ``homeassistant/<component>/.../config`` payloads are
  published on the first MQTT connect, built from the live settings-resolved
  registry. ``TestRuntimeDiscoveryPublication`` runs the real wiring through
  :class:`~cosalette.testing.AppHarness` and asserts the payloads land for a
  multi-word bulb name. ``TestStateTopicsAreReal`` cross-checks every generated
  ``state_topic`` against a topic the per-bulb telemetry tick actually
  publishes, via ``assert_discovery_topics_published`` (ADR-004).

The per-bulb entity name is a callable ``NameSpec`` keyed off
``settings.bulbs``; ``wiz2mqtt.schema.toml`` configures one bulb (``example``),
so the CLI output expands to three per-bulb entities plus the bridge.

Note: Lives in integration/ because it spawns a subprocess and reads from the
filesystem — not hermetic enough for the unit suite.

Test Techniques Used:
- Specification-based: the resolved schema must yield the documented HA entities
- Equivalence Partitioning: the read/write ``light`` + ``number`` vs the
  read-only ``power`` sensor (state_topic only, no command_topic)
- Cross-check: every discovery ``state_topic`` is verified against a topic the
  running telemetry device actually publishes, not a string re-derived from the
  same schema
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cosalette
import pytest
from cosalette import MockMqttClient
from cosalette.stores import MemoryStore
from cosalette.testing import AppHarness, FakeClock, assert_discovery_topics_published

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.entity import bulb_entity_tick
from wiz2mqtt.main import _bulb_map
from wiz2mqtt.models import WIZ_EFFECT_LIST, BulbSetCommand, BulbStateModel
from wiz2mqtt.ports import WizBulbPort
from wiz2mqtt.settings import BulbConfig, Wiz2MqttSettings
from wiz2mqtt.state import SharedState

# packages/tests/integration/<file> → app root is parents[3]
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schema.yaml"
BRIDGE_OBJECT_ID = "bridge"  # ADR-058 synthetic bridge sentinel
TOPIC_PREFIX = "wiz2mqtt"
SCHEMA_BULB = "example"  # matches apps/wiz2mqtt/wiz2mqtt.schema.toml
# Runtime tests build settings dynamically, so they exercise a multi-word bulb
# name the checked-in schema profile does not include. ``BulbConfig.name``
# permits underscores; ``effect_speed`` is itself an underscored object_id
# suffix — this guards the object_id -> device mapping against a single-token
# assumption creeping back in.
RUNTIME_BULBS = ("office", "living_room")
# The composite entity each ``ha_entities`` spec maps to: object_id suffix -> HA
# component. Declared once so the contract is not restated per test.
ENTITY_COMPONENTS = (
    ("light", "light"),
    ("effect_speed", "number"),
    ("power", "sensor"),
)
SUFFIXES = tuple(suffix for suffix, _ in ENTITY_COMPONENTS)
_WAIT_TIMEOUT = 3.0


def _expected_config_topics(names: tuple[str, ...]) -> set[str]:
    """The retained discovery ``config`` topics for *names* plus the bridge."""
    topics = {
        f"homeassistant/{component}/{TOPIC_PREFIX}/{bulb}_{suffix}/config"
        for bulb in names
        for suffix, component in ENTITY_COMPONENTS
    }
    topics.add(f"homeassistant/binary_sensor/{TOPIC_PREFIX}/bridge/config")
    return topics


# ---------------------------------------------------------------------------
# Offline HA discovery generation from docs/schema.yaml
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ha_payloads() -> list[dict[str, Any]]:
    """Run the schema ha-discovery CLI once and return the parsed payloads."""
    result = subprocess.run(
        [sys.executable, "-m", "cosalette", "schema", "ha-discovery", str(SCHEMA_PATH)],
        capture_output=True,
        text=True,
        check=True,
        env={
            k: os.environ[k]
            for k in ("PATH", "PYTHONPATH", "HOME", "VIRTUAL_ENV")
            if k in os.environ
        },
    )
    payloads = json.loads(result.stdout)
    assert payloads, "ha-discovery CLI returned no payloads"
    return payloads


@pytest.fixture(scope="module")
def entity_payloads(ha_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Discovery payloads for wiz2mqtt's own entities, without the bridge."""
    return [p for p in ha_payloads if p["config"]["object_id"] != BRIDGE_OBJECT_ID]


@pytest.fixture(scope="module")
def configs_by_id(entity_payloads: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index discovery payload configs by their object_id."""
    object_ids = [p["config"]["object_id"] for p in entity_payloads]
    dupes = [x for x, c in Counter(object_ids).items() if c > 1]
    assert not dupes, f"Duplicate object_ids emitted: {dupes}"
    return {p["config"]["object_id"]: p["config"] for p in entity_payloads}


@pytest.mark.integration
class TestHaDiscoveryGeneration:
    """Verify the model metadata produces valid HA MQTT discovery payloads."""

    def test_generates_one_entity_per_composite_spec_per_bulb(
        self, entity_payloads: list[dict[str, Any]]
    ) -> None:
        """Three composite specs × one configured bulb → three entities.

        Technique: Specification-based — one entity per ``ha_entities`` spec,
        not one per JSON property (composite entities skip per-property gen).
        """
        expected = {f"{SCHEMA_BULB}_{suffix}" for suffix in SUFFIXES}
        object_ids = {p["config"]["object_id"] for p in entity_payloads}
        assert object_ids == expected
        unique_ids = [p["config"]["unique_id"] for p in entity_payloads]
        assert all(unique_ids), "every entity must carry a non-empty unique_id"
        assert len(set(unique_ids)) == len(unique_ids), (
            "unique_ids must be collision-free — HA relies on them to dedupe"
        )

    def test_payloads_grouped_under_per_bulb_device(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """Every entity is grouped under its bulb's HA device (ADR-058).

        Technique: Specification-based — HA device grouping contract; the three
        components share one per-bulb ``device`` block.
        """
        for suffix in SUFFIXES:
            device = configs_by_id[f"{SCHEMA_BULB}_{suffix}"]["device"]
            assert device["identifiers"] == [f"cosalette_{TOPIC_PREFIX}_{SCHEMA_BULB}"]
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

    def test_light_entity_merges_state_and_command_topics(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The ``light`` carries both topics — the ``/state`` send channel and
        the ``/set`` receive channel merged into one entity (ADR-057).

        Technique: Specification-based — the JSON light schema superset plus the
        Option A static capability superset (per-bulb filtering deferred).
        """
        config = configs_by_id[f"{SCHEMA_BULB}_light"]
        assert config["schema"] == "json"
        assert config["state_topic"] == f"{TOPIC_PREFIX}/{SCHEMA_BULB}/state"
        assert config["command_topic"] == f"{TOPIC_PREFIX}/{SCHEMA_BULB}/set"
        assert config["brightness"] is True
        assert config["supported_color_modes"] == ["color_temp", "rgb"]
        assert config["effect_list"] == list(WIZ_EFFECT_LIST)
        assert (config["min_kelvin"], config["max_kelvin"]) == (2200, 6500)

    def test_effect_speed_number_is_bounded_and_shapes_json_command(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The effect-speed ``number`` is a read/write 10-200 slider.

        Technique: Boundary Value Analysis — the advertised min/max/step match
        pywizlight's accepted ``speed`` range.
        """
        config = configs_by_id[f"{SCHEMA_BULB}_effect_speed"]
        assert config["state_topic"] == f"{TOPIC_PREFIX}/{SCHEMA_BULB}/state"
        assert config["command_topic"] == f"{TOPIC_PREFIX}/{SCHEMA_BULB}/set"
        assert (config["min"], config["max"], config["step"]) == (10, 200, 1)
        assert config["command_template"] == '{"effect_speed": {{ value }}}'
        assert config["value_template"] == "{{ value_json.effect_speed }}"

    def test_power_sensor_is_read_only(
        self, configs_by_id: dict[str, dict[str, Any]]
    ) -> None:
        """The power ``sensor`` reads state only — no command_topic.

        Technique: Equivalence Partitioning — read-only telemetry vs the
        read/write light and number; ``BulbSetCommand`` omits the sensor spec.
        """
        config = configs_by_id[f"{SCHEMA_BULB}_power"]
        assert config["state_topic"] == f"{TOPIC_PREFIX}/{SCHEMA_BULB}/state"
        assert "command_topic" not in config
        assert config["device_class"] == "power"
        assert config["unit_of_measurement"] == "W"
        assert config["state_class"] == "measurement"
        assert config["value_template"] == "{{ value_json.power_draw_w }}"


# ---------------------------------------------------------------------------
# Runtime discovery publication via app.discovery()
# ---------------------------------------------------------------------------


def _make_settings(names: tuple[str, ...]) -> Wiz2MqttSettings:
    """Settings for the given bulb *names* with synthetic IPs."""
    return Wiz2MqttSettings(
        bulbs=[  # type: ignore[arg-type]
            {"name": name, "ip": f"10.0.0.{index + 2}"}
            for index, name in enumerate(names)
        ],
        _env_file=None,  # type: ignore[call-arg]
        _config_file=None,  # type: ignore[call-arg]
    )


def _build_discovery_app() -> cosalette.App:
    """Mirror ``wiz2mqtt.main``'s per-bulb telemetry wiring with ``app.discovery()``.

    Only the pieces discovery reads are registered: the per-bulb ``bulb_set``
    command (``payload_model=BulbSetCommand``) and ``bulb_entity`` telemetry
    (callable NameSpec, ``state_model=BulbStateModel``) — whose ``/set`` and
    ``/state`` channels the generator merges into one ``light`` — plus the
    ``SharedState`` factory. Backed by a ``MemoryStore`` so the test touches no
    disk. Both handler bodies are no-ops — the runtime publish path is
    exercised directly in ``TestStateTopicsAreReal``.
    """
    app = cosalette.App(
        name=TOPIC_PREFIX,
        version="0.0.0",
        settings_class=Wiz2MqttSettings,
        store=MemoryStore(),
    )
    app.discovery()

    @app.state
    def shared_state() -> SharedState:
        return SharedState()

    @app.command(
        name=_bulb_map,
        payload_model=BulbSetCommand,
        summary="Apply a partial state update to a bulb",
    )
    async def bulb_set(payload: str, config: BulbConfig) -> None:
        return None

    @app.telemetry(
        name=_bulb_map,
        interval=3600.0,
        triggerable="local",
        summary="Per-bulb state publisher",
        state_model=BulbStateModel,
    )
    async def bulb_entity(
        ctx: cosalette.DeviceContext,
        config: BulbConfig,
        state: SharedState,
    ) -> BulbStateModel | None:
        return None

    return app


@pytest.fixture
def runtime_harness() -> AppHarness:
    """AppHarness whose bulb set includes a multi-word name (``living_room``)."""
    return AppHarness(
        app=_build_discovery_app(),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=_make_settings(RUNTIME_BULBS),
        shutdown_event=asyncio.Event(),
    )


@pytest.fixture
def schema_harness() -> AppHarness:
    """AppHarness over the single ``example`` bulb the checked-in schema uses.

    Its ground-truth publishes must line up with the offline ``ha_payloads``
    generated from ``wiz2mqtt.schema.toml``.
    """
    return AppHarness(
        app=_build_discovery_app(),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=_make_settings((SCHEMA_BULB,)),
        shutdown_event=asyncio.Event(),
    )


async def _run_until_discovery_published(
    harness: AppHarness, expected: set[str]
) -> None:
    """Start the harness, wait until *all* expected config topics land, shut down.

    Uses the harness's deterministic ``wait_for_publish_count`` (which yields to
    the event loop rather than sleeping on the wall clock) so the wait never
    races a fixed timeout. The discovery config topics are published in one
    burst on first connect, so awaiting each ``expected`` topic in turn settles
    once that burst has landed.
    """
    task = asyncio.create_task(harness.run())
    try:
        for topic in expected:
            await harness.wait_for_publish_count(topic, 1)
    finally:
        harness.shutdown_event.set()
        await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)


@pytest.mark.integration
class TestRuntimeDiscoveryPublication:
    """app.discovery() publishes retained HA config topics on first connect."""

    async def test_publishes_retained_config_topic_per_entity(
        self, runtime_harness: AppHarness
    ) -> None:
        """One retained config topic per composite entity, per bulb, plus bridge.

        Exercises a multi-word bulb name (``living_room``) so the object_id ->
        topic mapping is verified for underscored names.

        Technique: Specification-based — ADR-059 runtime publication contract,
        against the live registry rather than the checked-in schema.
        """
        expected = _expected_config_topics(RUNTIME_BULBS)
        await _run_until_discovery_published(runtime_harness, expected)

        published = {
            topic: retain
            for topic, _payload, retain, _qos in runtime_harness.mqtt.published
        }
        discovery = {t for t in published if t.startswith("homeassistant/")}
        assert discovery == expected, "runtime discovery topics must match exactly"
        assert all(published[topic] for topic in expected), "config topics must retain"

    async def test_config_payload_targets_real_state_topic(
        self, runtime_harness: AppHarness
    ) -> None:
        """A published config points HA at the bulb's real state/command topics.

        ``living_room`` confirms the topics are built from the full, underscored
        bulb name rather than a truncated token.

        Technique: Specification-based — the discovery payload is self-consistent
        with the app's own topic layout.
        """
        await _run_until_discovery_published(
            runtime_harness, _expected_config_topics(RUNTIME_BULBS)
        )

        topic = f"homeassistant/light/{TOPIC_PREFIX}/living_room_light/config"
        payload = next(p for t, p, *_ in runtime_harness.mqtt.published if t == topic)
        config = json.loads(payload)
        assert config["state_topic"] == f"{TOPIC_PREFIX}/living_room/state"
        assert config["command_topic"] == f"{TOPIC_PREFIX}/living_room/set"
        assert config["schema"] == "json"


@pytest.mark.integration
class TestStateTopicsAreReal:
    """Every discovery state_topic matches a topic a bulb telemetry tick publishes."""

    async def test_state_topics_match_actual_runtime_publishes(
        self,
        schema_harness: AppHarness,
        ha_payloads: list[dict[str, Any]],
    ) -> None:
        """Cross-check the generated payloads against real publishes.

        Drives :func:`wiz2mqtt.entity.bulb_entity_tick` directly against a
        :class:`~wiz2mqtt.adapters.fake.FakeWizBulbAdapter` so the per-bulb
        device publishes ``{prefix}/{bulb}/state``.
        ``assert_discovery_topics_published`` (ADR-004) then fails if any
        discovery ``state_topic`` was never published at runtime.

        Technique: Cross-check — schema-derived expectation validated against
        runtime ground truth, not another string derived from the same schema.
        """
        expected_config = _expected_config_topics((SCHEMA_BULB,))
        task = asyncio.create_task(schema_harness.run())
        try:
            for topic in expected_config:
                await schema_harness.wait_for_publish_count(topic, 1)
            port: WizBulbPort = FakeWizBulbAdapter()
            state = SharedState()
            config = schema_harness.settings.bulbs[0]
            ctx = cosalette.DeviceContext(
                name=SCHEMA_BULB,
                settings=schema_harness.settings,
                mqtt=schema_harness.mqtt,
                topic_prefix=TOPIC_PREFIX,
                shutdown_event=schema_harness.shutdown_event,
                adapters={},
                clock=schema_harness.clock,
                state_model=BulbStateModel,
            )
            payload = await bulb_entity_tick(ctx, config, port, state)
            assert payload is not None
            await ctx.publish_state(BulbStateModel.model_validate(payload))
        finally:
            schema_harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)

        payloads = [SimpleNamespace(config=p["config"]) for p in ha_payloads]
        assert_discovery_topics_published(schema_harness, payloads)
