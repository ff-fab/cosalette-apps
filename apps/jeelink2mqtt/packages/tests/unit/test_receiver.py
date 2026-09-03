"""Unit tests for jeelink2mqtt.receiver — module-level helper functions.

Test Techniques Used:
- Specification-based Testing: JSON structure, retain flags, rounding rules
- Boundary Value Analysis: heartbeat interval thresholds, staleness edge cases
- Decision Table Testing: sensor_entity_tick branch combinations
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from jeelink2mqtt.app import SharedState
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import MappingEvent, SensorConfig, SensorReading
from jeelink2mqtt.receiver import (
    publish_mapping_event,
    publish_mapping_state,
    publish_raw_diagnostic,
    sensor_entity_tick,
)
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from tests.fixtures.doubles import FakeDeviceContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device_store(initial_data: dict | None = None) -> DeviceStore:
    """Create an in-memory DeviceStore for testing."""
    store_data = {"": initial_data} if initial_data else None
    backend = MemoryStore(initial=store_data)
    ds = DeviceStore(backend=backend, key="")
    ds.load()
    return ds


def _make_settings(
    *,
    sensor_names: list[str] | None = None,
    staleness_timeout: float = 600.0,
    heartbeat_interval: float = 180.0,
) -> Jeelink2MqttSettings:
    """Build settings with the given sensor names."""
    names = sensor_names or ["office", "outdoor"]
    return Jeelink2MqttSettings(
        serial_port="/dev/ttyUSB0",
        staleness_timeout_seconds=staleness_timeout,
        heartbeat_interval_seconds=heartbeat_interval,
        sensors=[SensorConfigSettings(name=n) for n in names],
    )


def _make_shared_state(
    sensor_configs: list[SensorConfig] | None = None,
    staleness_timeout: float = 600.0,
    window: int = 3,
) -> SharedState:
    """Build a SharedState with a fresh registry and filter bank."""
    configs = sensor_configs or [
        SensorConfig(name="office"),
        SensorConfig(name="outdoor"),
    ]
    return SharedState(
        registry=SensorRegistry(sensors=configs, staleness_timeout=staleness_timeout),
        filter_bank=FilterBank(window=window),
        sensor_configs={c.name: c for c in configs},
    )


def _fixed_reading(
    *,
    sensor_id: int = 42,
    temperature: float = 21.5,
    humidity: int = 55,
    low_battery: bool = False,
    timestamp: datetime | None = None,
) -> SensorReading:
    """Create a SensorReading with a fixed or given timestamp."""
    return SensorReading(
        sensor_id=sensor_id,
        temperature=temperature,
        humidity=humidity,
        low_battery=low_battery,
        timestamp=timestamp or datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
    )


# ===========================================================================
# publish_raw_diagnostic
# ===========================================================================


@pytest.mark.unit
class TestPublishRaw:
    """Verifies raw diagnostic publish format and retain=False."""

    async def test_publishes_json_to_raw_state(self) -> None:
        """Publishes reading as JSON to 'raw/state', non-retained.

        Technique: Specification-based — topic, payload structure, retain flag.
        """
        # Arrange
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        reading = _fixed_reading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            timestamp=ts,
        )
        ctx = FakeDeviceContext()

        # Act
        await publish_raw_diagnostic(ctx, reading)

        # Assert
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "raw/state"
        assert retain is False

        data = json.loads(payload)
        assert data["sensor_id"] == 42
        assert data["temperature"] == 21.5
        assert data["humidity"] == 55
        assert data["low_battery"] is False
        assert data["timestamp"] == ts.isoformat()

    async def test_publishes_low_battery_flag(self) -> None:
        """low_battery is faithfully serialised in the JSON payload.

        Technique: Equivalence Partitioning — True vs False battery flag.
        """
        # Arrange
        reading = _fixed_reading(low_battery=True)
        ctx = FakeDeviceContext()

        # Act
        await publish_raw_diagnostic(ctx, reading)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data["low_battery"] is True


# ===========================================================================
# publish_mapping_event
# ===========================================================================


@pytest.mark.unit
class TestPublishMappingEvent:
    """Verifies mapping event publish format and retain=False."""

    async def test_publishes_event_json(self) -> None:
        """Publishes MappingEvent as JSON to 'mapping/event', non-retained.

        Technique: Specification-based — JSON structure matches event fields.
        """
        # Arrange
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name="office",
            old_sensor_id=None,
            new_sensor_id=42,
            timestamp=ts,
            reason="First reading from sensor ID 42",
        )
        ctx = FakeDeviceContext()

        # Act
        await publish_mapping_event(ctx, event)

        # Assert
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "mapping/event"
        assert retain is False

        data = json.loads(payload)
        assert data["event_type"] == "auto_adopt"
        assert data["sensor_name"] == "office"
        assert data["old_sensor_id"] is None
        assert data["new_sensor_id"] == 42
        assert data["timestamp"] == ts.isoformat()
        assert data["reason"] == "First reading from sensor ID 42"

    async def test_old_sensor_id_included_for_replacement(self) -> None:
        """When a mapping replaces an old ID, both IDs appear in the event.

        Technique: Equivalence Partitioning — replacement vs first-assign.
        """
        # Arrange
        event = MappingEvent(
            event_type="auto_adopt",
            sensor_name="office",
            old_sensor_id=10,
            new_sensor_id=42,
            timestamp=datetime.now(UTC),
            reason="Battery swap detected",
        )
        ctx = FakeDeviceContext()

        # Act
        await publish_mapping_event(ctx, event)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data["old_sensor_id"] == 10
        assert data["new_sensor_id"] == 42


# ===========================================================================
# publish_mapping_state
# ===========================================================================


@pytest.mark.unit
class TestPublishMappingState:
    """Verifies mapping state snapshot publish format and retain=True."""

    async def test_publishes_mapping_snapshot(self) -> None:
        """Publishes all current mappings as JSON to 'mapping/state', retained.

        Technique: Specification-based — snapshot reflects registry state.
        """
        # Arrange — use explicit assign for a deterministic mapping
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs)
        state.registry.assign("office", 42)
        state.registry.drain_events()

        ctx = FakeDeviceContext()

        # Act
        await publish_mapping_state(ctx, state)

        # Assert
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "mapping/state"
        assert retain is True

        data = json.loads(payload)
        assert "office" in data
        assert data["office"]["sensor_id"] == 42

    async def test_empty_registry_publishes_empty_object(self) -> None:
        """When no mappings exist, publishes an empty JSON object.

        Technique: Boundary Value Analysis — empty state edge case.
        """
        # Arrange
        state = _make_shared_state()
        ctx = FakeDeviceContext()

        # Act
        await publish_mapping_state(ctx, state)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data == {}


# ===========================================================================
# sensor_entity_tick
# ===========================================================================


@pytest.mark.unit
class TestSensorEntityTick:
    """Covers the branch combinations in sensor_entity_tick."""

    async def test_stale_sensor_marked_unavailable(self) -> None:
        """A sensor with no mapping (stale) triggers mark_unavailable().

        Technique: Specification-based — unmapped sensor is always stale.
        """
        # Arrange — no mapping → stale
        configs = [SensorConfig(name="office")]
        settings = _make_settings(sensor_names=["office"])
        state = _make_shared_state(sensor_configs=configs)
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert
        assert ctx.availability_calls == ["unavailable"]
        assert state.last_availability["office"] == "offline"
        assert ctx.published_state == []

    async def test_already_offline_not_re_marked(self) -> None:
        """A sensor already marked offline is not re-marked on each tick.

        Technique: Equivalence Partitioning — deduplication of retained offline
        publishes. Without this guard, the handler would spam the MQTT broker
        with identical retained messages every second while a sensor stays stale.
        """
        # Arrange — stale sensor whose availability was already published
        configs = [SensorConfig(name="office")]
        settings = _make_settings(sensor_names=["office"])
        state = _make_shared_state(sensor_configs=configs)
        state.last_availability["office"] = "offline"  # already published
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert — no duplicate mark_unavailable() call
        assert ctx.availability_calls == []

    async def test_recovery_marks_available_once(self) -> None:
        """A previously-offline sensor that's fresh again is marked available.

        Technique: State Transition Testing — offline → online recovery path.
        """
        # Arrange — sensor is fresh (mapped) but was last marked offline
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)
        state.last_availability["office"] = "offline"

        settings = _make_settings(sensor_names=["office"])
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert
        assert ctx.availability_calls == ["available"]
        assert state.last_availability["office"] == "online"

    async def test_already_online_not_re_marked(self) -> None:
        """A sensor already online is not re-marked available on each tick.

        Technique: Equivalence Partitioning — deduplication of availability calls.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)
        state.last_availability["office"] = "online"

        settings = _make_settings(sensor_names=["office"])
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert
        assert ctx.availability_calls == []

    async def test_not_stale_but_no_cached_reading_publishes_nothing(self) -> None:
        """A fresh mapping with no cached reading yet publishes nothing.

        Technique: Equivalence Partitioning — no reading cached path.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"])
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=True)

        # Assert
        assert ctx.published_state == []

    async def test_fresh_reading_publishes_state(self) -> None:
        """A calibrated reading newer than the last publish is published.

        Technique: Specification-based — full happy path.
        """
        # Arrange — map 'office' so it's not stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        mapping_reading = _fixed_reading(sensor_id=42, timestamp=now)
        state.registry.record_reading(mapping_reading)

        reading = _fixed_reading(temperature=21.567, humidity=55, timestamp=now)
        state.last_readings["office"] = reading

        settings = _make_settings(sensor_names=["office"])
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=True)

        # Assert
        assert len(ctx.published_state) == 1
        payload = ctx.published_state[0]
        assert payload["temperature"] == 21.57  # rounded to 2 decimals
        assert payload["humidity"] == 55
        assert payload["low_battery"] is False
        assert payload["timestamp"] == now.isoformat()
        assert state.last_publish_time["office"] is not None

    async def test_stale_reading_not_republished_before_heartbeat_due(self) -> None:
        """An already-published reading is not re-published before the
        heartbeat interval elapses.

        Technique: Boundary Value Analysis — just below threshold.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        state.registry.record_reading(_fixed_reading(sensor_id=42, timestamp=now))

        reading = _fixed_reading(timestamp=now)
        state.last_readings["office"] = reading
        state.last_publish_time["office"] = now  # already published this reading

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert — neither fresh nor heartbeat-due → nothing published
        assert ctx.published_state == []

    async def test_heartbeat_republishes_unchanged_reading(self) -> None:
        """When the heartbeat interval has elapsed, the last reading is
        re-published even though it isn't newer than the last publish.

        Technique: Decision Table Testing — heartbeat-due branch.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        state.registry.record_reading(_fixed_reading(sensor_id=42, timestamp=now))

        reading = _fixed_reading(timestamp=now)
        state.last_readings["office"] = reading
        # Last publish was 200s ago — past the 180s heartbeat interval, and no
        # wake arrived, so only the heartbeat can fire.
        state.last_publish_time["office"] = now - timedelta(seconds=200)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert
        assert len(ctx.published_state) == 1
        assert state.last_publish_time["office"] > now - timedelta(seconds=200)

    async def test_trigger_publishes_reading_older_than_last_publish(self) -> None:
        """A wake publishes regardless of the publish wall-clock.

        Regression for the interleaving race (PR #206 review): the stream can
        cache a reading whose own timestamp predates ``last_publish_time``
        (set to the tick's wall-clock at publish). The wake — not a timestamp
        comparison — is the freshness signal, so such a reading publishes
        instead of stalling until the next heartbeat.

        Technique: Decision Table — triggered=True, heartbeat not due.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        state.registry.record_reading(_fixed_reading(sensor_id=42, timestamp=now))

        state.last_readings["office"] = _fixed_reading(
            timestamp=now - timedelta(seconds=1)
        )
        state.last_publish_time["office"] = now  # published a moment ago

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        # Act
        await sensor_entity_tick(ctx, "office", settings, state, triggered=True)

        # Assert
        assert len(ctx.published_state) == 1

    async def test_never_published_reading_publishes_without_a_trigger(self) -> None:
        """A cached reading that was never published publishes on a timeout.

        Recovery path: a wake coalesces, so one consumed by a publish that
        raised would otherwise strand the sensor until its next frame. With no
        ``last_publish_time``, the heartbeat is due immediately.

        Technique: Boundary Value Analysis — last_publish_time absent.
        """
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        state.registry.record_reading(_fixed_reading(sensor_id=42, timestamp=now))
        state.last_readings["office"] = _fixed_reading(timestamp=now)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        # Act — no wake, no prior publish
        await sensor_entity_tick(ctx, "office", settings, state, triggered=False)

        # Assert
        assert len(ctx.published_state) == 1
        assert state.last_publish_time["office"] is not None


# ===========================================================================
# SharedState methods (cosalette 0.3.13 refactor)
# ===========================================================================


@pytest.mark.unit
class TestSharedStateRestoreFrom:
    """Test SharedState.restore_from method."""

    def test_restores_registry_from_valid_data(self) -> None:
        """restore_from rebuilds registry from store data.

        Technique: Specification-based — persistence contract.
        """
        # Arrange
        config = SensorConfig(name="office")
        state = _make_shared_state(sensor_configs=[config])

        registry_data = {
            "mappings": {
                "office": {
                    "sensor_id": 42,
                    "sensor_name": "office",
                    "mapped_at": "2025-01-01T00:00:00+00:00",
                    "last_seen": "2025-01-01T00:00:00+00:00",
                }
            },
            "unmapped": {},
        }
        store = _make_device_store(initial_data={"registry": registry_data})
        settings = _make_settings(sensor_names=["office"])

        # Act
        state.restore_from(store, settings)

        # Assert
        mappings = state.registry.get_all_mappings()
        assert "office" in mappings
        assert mappings["office"].sensor_id == 42

    def test_handles_missing_registry_data(self) -> None:
        """restore_from handles missing registry key gracefully.

        Technique: Error Guessing — missing data.
        """
        # Arrange
        config = SensorConfig(name="office")
        state = _make_shared_state(sensor_configs=[config])
        store = _make_device_store()  # Empty store
        settings = _make_settings(sensor_names=["office"])

        # Act
        state.restore_from(store, settings)

        # Assert — no exception, registry remains empty
        mappings = state.registry.get_all_mappings()
        assert len(mappings) == 0

    def test_handles_corrupt_registry_data(self) -> None:
        """restore_from falls back gracefully when from_dict raises on corrupt schema.

        Technique: Error Guessing — valid dict type but wrong internal schema
        causes SensorRegistry.from_dict() to raise KeyError.
        """
        # Arrange
        config = SensorConfig(name="office")
        state = _make_shared_state(sensor_configs=[config])
        # Valid dict but missing required "sensor_id" key inside mappings
        registry_data = {"mappings": {"office": {"sensor_name": "office"}}}
        store = _make_device_store(initial_data={"registry": registry_data})
        settings = _make_settings(sensor_names=["office"])

        # Act — must not raise
        state.restore_from(store, settings)

        # Assert — falls back to fresh empty registry
        mappings = state.registry.get_all_mappings()
        assert len(mappings) == 0

    def test_invalid_data_not_dict_keeps_fresh_registry(self) -> None:
        """When stored registry is not a dict, state.registry is unchanged.

        Technique: Equivalence Partitioning — invalid data branch in restore_from.
        """
        # Arrange
        config = SensorConfig(name="office")
        state = _make_shared_state(sensor_configs=[config])
        store = _make_device_store(initial_data={"registry": "not-a-dict"})
        settings = _make_settings(sensor_names=["office"])
        original_registry = state.registry

        # Act
        state.restore_from(store, settings)

        # Assert — registry object unchanged (same identity)
        assert state.registry is original_registry


@pytest.mark.unit
class TestSharedStatePersistRegistryIfDue:
    """Test SharedState.persist_registry_if_due method."""

    def test_persists_when_interval_elapsed(self) -> None:
        """persist_registry_if_due persists when interval has passed.

        Technique: Specification-based — time threshold behavior.
        """
        # Arrange
        state = _make_shared_state()
        store = _make_device_store()
        now = datetime.now(UTC)
        last_persist = now - timedelta(seconds=120)  # 2 minutes ago

        # Act
        result = state.persist_registry_if_due(
            store, now, last_persist, 60
        )  # 1 minute interval

        # Assert
        assert result == now  # Returns new persist time
        assert "registry" in store  # Registry was persisted

    def test_does_not_persist_when_interval_not_elapsed(self) -> None:
        """persist_registry_if_due does not persist when interval hasn't passed.

        Technique: Specification-based — time threshold behavior.
        """
        # Arrange
        state = _make_shared_state()
        store = _make_device_store()
        now = datetime.now(UTC)
        last_persist = now - timedelta(seconds=30)  # 30 seconds ago

        # Act
        result = state.persist_registry_if_due(
            store, now, last_persist, 60
        )  # 1 minute interval

        # Assert
        assert result is None  # No persist occurred
        assert "registry" not in store  # Registry was not persisted


# ===========================================================================
# SharedState.record_calibrated_reading
# ===========================================================================


@pytest.mark.unit
class TestRecordCalibratedReading:
    """Verifies SharedState.record_calibrated_reading side effects."""

    def test_stores_reading(self) -> None:
        """record_calibrated_reading caches the reading.

        Technique: Specification-based — state mutation contract.
        """
        # Arrange
        state = _make_shared_state(sensor_configs=[SensorConfig(name="office")])
        reading = _fixed_reading(sensor_id=42)

        # Act
        state.record_calibrated_reading("office", reading)

        # Assert — exact object identity, not just equality
        assert state.last_readings["office"] is reading

    def test_does_not_touch_availability(self) -> None:
        """record_calibrated_reading leaves availability untouched.

        Technique: Specification-based — availability is owned exclusively
        by sensor_entity_tick, not by the stream's calibration caching.
        """
        # Arrange
        state = _make_shared_state(sensor_configs=[SensorConfig(name="office")])
        state.last_availability["office"] = "offline"
        reading = _fixed_reading(sensor_id=42)

        # Act
        state.record_calibrated_reading("office", reading)

        # Assert — availability is unchanged
        assert state.last_availability["office"] == "offline"
