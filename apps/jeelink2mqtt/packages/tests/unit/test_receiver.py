"""Unit tests for jeelink2mqtt.receiver — module-level helper functions.

Test Techniques Used:
- Equivalence Partitioning: valid/invalid/missing data for _restore_registry
- Specification-based Testing: JSON structure, retain flags, rounding rules
- Boundary Value Analysis: heartbeat interval thresholds, staleness edge cases
- State Transition Testing: filter bank + calibration pipeline composition
- Decision Table Testing: _maybe_heartbeat branch combinations
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
    _apply_pipeline,
    _check_staleness,
    _maybe_heartbeat,
    _publish_mapping_event,
    _publish_mapping_state,
    _publish_raw,
    _publish_sensor,
    _restore_registry,
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
# _apply_pipeline
# ===========================================================================


@pytest.mark.unit
class TestApplyPipeline:
    """Verifies filter → calibrate composition in _apply_pipeline."""

    def test_applies_filter_then_calibration(self) -> None:
        """Pipeline feeds reading through filter bank, then calibrates.

        Technique: Specification-based — verifies composition of two
        operations (median filter + calibration offset).
        """
        # Arrange
        config = SensorConfig(name="office", temp_offset=1.0, humidity_offset=2.0)
        state = _make_shared_state(sensor_configs=[config], window=3)
        reading = _fixed_reading(sensor_id=42, temperature=20.0, humidity=50)

        # Act — first call through window=3 median: output equals input
        result = _apply_pipeline(reading, config, state)

        # Assert — filter passes through (window not full), offset applied
        assert result.temperature == pytest.approx(21.0)  # 20.0 + 1.0
        assert result.humidity == 52  # 50 + floor(2.0 + 0.5)

    def test_preserves_metadata_fields(self) -> None:
        """Pipeline preserves sensor_id, low_battery, timestamp.

        Technique: Specification-based — dataclasses.replace contract.
        """
        # Arrange
        ts = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)
        config = SensorConfig(name="office", temp_offset=0.5)
        state = _make_shared_state(sensor_configs=[config], window=3)
        reading = _fixed_reading(sensor_id=99, low_battery=True, timestamp=ts)

        # Act
        result = _apply_pipeline(reading, config, state)

        # Assert
        assert result.sensor_id == 99
        assert result.low_battery is True
        assert result.timestamp == ts

    def test_zero_offsets_only_filters(self) -> None:
        """With zero calibration offsets, output equals filtered values.

        Technique: Equivalence Partitioning — identity calibration class.
        """
        # Arrange
        config = SensorConfig(name="office")
        state = _make_shared_state(sensor_configs=[config], window=3)
        reading = _fixed_reading(temperature=22.0, humidity=60)

        # Act
        result = _apply_pipeline(reading, config, state)

        # Assert — first through a window=3 median, single value = itself
        assert result.temperature == pytest.approx(22.0)
        assert result.humidity == 60


# ===========================================================================
# _restore_registry
# ===========================================================================


@pytest.mark.unit
class TestRestoreRegistry:
    """Covers the three branches: None, not-dict, valid dict."""

    def test_no_persisted_data_keeps_fresh_registry(self) -> None:
        """When store has no 'registry' key, state.registry is unchanged.

        Technique: Equivalence Partitioning — empty/absent data branch.
        """
        # Arrange
        store = _make_device_store()  # No initial data
        state = _make_shared_state()
        settings = _make_settings()
        original_registry = state.registry

        # Act
        _restore_registry(store, state, settings)

        # Assert — registry object unchanged (same identity)
        assert state.registry is original_registry

    def test_invalid_data_not_dict_keeps_fresh_registry(self) -> None:
        """When stored registry is not a dict, state.registry is unchanged.

        Technique: Equivalence Partitioning — invalid data branch.
        """
        # Arrange — persist a non-dict value under "registry"
        store = _make_device_store(initial_data={"registry": "not-a-dict"})
        state = _make_shared_state()
        settings = _make_settings()
        original_registry = state.registry

        # Act
        _restore_registry(store, state, settings)

        # Assert — registry object unchanged
        assert state.registry is original_registry

    def test_valid_dict_restores_registry(self) -> None:
        """When stored registry is a valid dict, a new registry is built.

        Technique: Specification-based — SensorRegistry.from_dict is used.
        """
        # Arrange
        now = datetime.now(UTC)
        registry_snapshot = {
            "mappings": {
                "office": {
                    "sensor_id": 42,
                    "sensor_name": "office",
                    "mapped_at": now.isoformat(),
                    "last_seen": now.isoformat(),
                },
            },
            "unmapped": {},
        }
        store = _make_device_store(initial_data={"registry": registry_snapshot})
        state = _make_shared_state()
        settings = _make_settings()

        # Act
        _restore_registry(store, state, settings)

        # Assert — registry was replaced, mappings restored
        mappings = state.registry.get_all_mappings()
        assert "office" in mappings
        assert mappings["office"].sensor_id == 42


# ===========================================================================
# _publish_raw
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
        await _publish_raw(ctx, reading)

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
        await _publish_raw(ctx, reading)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data["low_battery"] is True


# ===========================================================================
# _publish_sensor
# ===========================================================================


@pytest.mark.unit
class TestPublishSensor:
    """Verifies calibrated sensor publish format and retain=True."""

    async def test_publishes_retained_json(self) -> None:
        """Publishes to '{name}/state' with retain=True.

        Technique: Specification-based — topic pattern and retain flag.
        """
        # Arrange
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        reading = _fixed_reading(temperature=21.567, humidity=55, timestamp=ts)
        ctx = FakeDeviceContext()

        # Act
        await _publish_sensor(ctx, "office", reading)

        # Assert
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "office/state"
        assert retain is True

        data = json.loads(payload)
        assert data["temperature"] == 21.57  # rounded to 2 decimals
        assert data["humidity"] == 55
        assert data["low_battery"] is False
        assert data["timestamp"] == ts.isoformat()

    async def test_rounds_temperature_to_two_decimals(self) -> None:
        """Temperature is rounded to 2 decimal places in published JSON.

        Technique: Boundary Value Analysis — rounding precision.
        """
        # Arrange
        reading = _fixed_reading(temperature=21.555)
        ctx = FakeDeviceContext()

        # Act
        await _publish_sensor(ctx, "test", reading)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data["temperature"] == round(21.555, 2)

    async def test_sensor_name_in_topic(self) -> None:
        """Topic uses the provided sensor name.

        Technique: Specification-based — topic templating.
        """
        # Arrange
        reading = _fixed_reading()
        ctx = FakeDeviceContext()

        # Act
        await _publish_sensor(ctx, "outdoor", reading)

        # Assert
        assert ctx.published[0][0] == "outdoor/state"


# ===========================================================================
# _publish_mapping_event
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
        await _publish_mapping_event(ctx, event)

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
        await _publish_mapping_event(ctx, event)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data["old_sensor_id"] == 10
        assert data["new_sensor_id"] == 42


# ===========================================================================
# _publish_mapping_state
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
        await _publish_mapping_state(ctx, state)

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
        await _publish_mapping_state(ctx, state)

        # Assert
        data = json.loads(ctx.published[0][1])
        assert data == {}


# ===========================================================================
# _check_staleness
# ===========================================================================


@pytest.mark.unit
class TestCheckStaleness:
    """Verifies offline availability publishing for stale sensors."""

    async def test_stale_sensor_gets_offline(self) -> None:
        """A sensor with no mapping (stale) triggers 'offline' availability.

        Technique: Specification-based — unmapped sensor is always stale.
        """
        # Arrange — settings and state both have only 'office'
        configs = [SensorConfig(name="office")]
        settings = _make_settings(sensor_names=["office"])
        state = _make_shared_state(sensor_configs=configs)  # No mappings → stale
        ctx = FakeDeviceContext()

        # Act
        await _check_staleness(ctx, settings, state)

        # Assert — one offline publish for the single configured sensor
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "office/availability"
        assert payload == "offline"
        assert retain is True

    async def test_non_stale_sensor_skipped(self) -> None:
        """A recently-seen sensor does NOT get 'offline' published.

        Technique: Equivalence Partitioning — non-stale path.
        """
        # Arrange — create a state with a recent mapping
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"])
        ctx = FakeDeviceContext()

        # Act
        await _check_staleness(ctx, settings, state)

        # Assert — nothing published (sensor is fresh)
        assert len(ctx.published) == 0

    async def test_mix_stale_and_fresh(self) -> None:
        """Only stale sensors get offline; fresh ones are skipped.

        Technique: Decision Table Testing — mixed staleness states.
        """
        # Arrange — two sensors: office (mapped/fresh), outdoor (unmapped/stale)
        configs = [SensorConfig(name="office"), SensorConfig(name="outdoor")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        # Manually assign 'office' so it has a fresh mapping
        state.registry.assign("office", 42)
        state.registry.drain_events()

        settings = _make_settings(sensor_names=["office", "outdoor"])
        ctx = FakeDeviceContext()

        # Act
        await _check_staleness(ctx, settings, state)

        # Assert — only 'outdoor' (unmapped/stale) gets offline
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "outdoor/availability"
        assert payload == "offline"
        assert retain is True


# ===========================================================================
# _maybe_heartbeat
# ===========================================================================


@pytest.mark.unit
class TestMaybeHeartbeat:
    """Covers the branch combinations in _maybe_heartbeat."""

    async def test_stale_sensor_skipped(self) -> None:
        """Stale sensors are not heartbeated.

        Technique: Decision Table — stale = True → skip.
        """
        # Arrange — no mapping → stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs)
        settings = _make_settings(sensor_names=["office"], heartbeat_interval=10.0)
        ctx = FakeDeviceContext()

        last_readings: dict[str, SensorReading] = {}
        last_publish_time: dict[str, datetime] = {}

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — nothing published
        assert len(ctx.published) == 0

    async def test_interval_not_elapsed_skipped(self) -> None:
        """When heartbeat interval hasn't elapsed, nothing is published.

        Technique: Boundary Value Analysis — just below threshold.
        """
        # Arrange — map 'office' so it's not stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        last_readings: dict[str, SensorReading] = {"office": reading}
        last_publish_time: dict[str, datetime] = {
            "office": datetime.now(UTC),  # Just now
        }

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — interval not elapsed → nothing published
        assert len(ctx.published) == 0

    async def test_no_last_publish_time_skipped(self) -> None:
        """When there's no last_publish_time entry, the sensor is skipped.

        Technique: Equivalence Partitioning — missing time entry path.
        The code checks `last_time is None` and uses `or` with the interval
        check, so None means the condition short-circuits to continue.
        """
        # Arrange — map 'office' so it's not stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        reading = _fixed_reading(sensor_id=42, timestamp=datetime.now(UTC))
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=180.0)
        ctx = FakeDeviceContext()

        last_readings: dict[str, SensorReading] = {"office": reading}
        last_publish_time: dict[str, datetime] = {}  # No entry at all

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — no last_time → condition triggers continue
        assert len(ctx.published) == 0

    async def test_interval_elapsed_with_last_reading_publishes(self) -> None:
        """When interval elapsed and last reading exists, re-publishes.

        Technique: Specification-based — full happy path.
        """
        # Arrange — map 'office' so it's not stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        reading = _fixed_reading(sensor_id=42, timestamp=now)
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=10.0)
        ctx = FakeDeviceContext()

        last_readings: dict[str, SensorReading] = {"office": reading}
        # Last publish was 30 seconds ago → well past 10s interval
        last_publish_time: dict[str, datetime] = {"office": now - timedelta(seconds=30)}

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — sensor state re-published + availability online
        assert len(ctx.published) == 2
        topics = [t for t, _, _ in ctx.published]
        assert "office/state" in topics
        assert "office/availability" in topics

        # Verify availability message
        for topic, payload, retain in ctx.published:
            if topic == "office/availability":
                assert payload == "online"
                assert retain is True

    async def test_interval_elapsed_without_last_reading_publishes_availability_only(
        self,
    ) -> None:
        """When interval elapsed but no last reading, only availability is published.

        Technique: Decision Table — interval elapsed + no cached reading.
        """
        # Arrange — map 'office' so it's not stale
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        reading = _fixed_reading(sensor_id=42, timestamp=now)
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=10.0)
        ctx = FakeDeviceContext()

        last_readings: dict[str, SensorReading] = {}  # No cached reading
        last_publish_time: dict[str, datetime] = {"office": now - timedelta(seconds=30)}

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — only availability, no state re-publish
        assert len(ctx.published) == 1
        topic, payload, retain = ctx.published[0]
        assert topic == "office/availability"
        assert payload == "online"
        assert retain is True

    async def test_updates_last_publish_time(self) -> None:
        """After heartbeat, last_publish_time is updated to now.

        Technique: State Transition Testing — side effect verification.
        """
        # Arrange
        configs = [SensorConfig(name="office")]
        state = _make_shared_state(sensor_configs=configs, staleness_timeout=600.0)
        now = datetime.now(UTC)
        reading = _fixed_reading(sensor_id=42, timestamp=now)
        state.registry.record_reading(reading)

        settings = _make_settings(sensor_names=["office"], heartbeat_interval=10.0)
        ctx = FakeDeviceContext()

        old_time = now - timedelta(seconds=30)
        last_readings: dict[str, SensorReading] = {"office": reading}
        last_publish_time: dict[str, datetime] = {"office": old_time}

        # Act
        await _maybe_heartbeat(ctx, settings, state, last_readings, last_publish_time)

        # Assert — last_publish_time updated (newer than old_time)
        assert last_publish_time["office"] > old_time
