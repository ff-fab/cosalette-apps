"""Integration tests for the jeelink2mqtt application layer.

Tests the cosalette application wiring: ``app.py`` (lifespan, factory,
sensor config builder), ``commands.py`` (handle_mapping dispatch
wrapper), and ``receiver.py`` (main receiver loop).

These tests exercise the *registered* handlers extracted from the
cosalette ``App``, verifying that the decorator-based wiring works
end-to-end with real domain objects and in-memory test doubles.

Test Techniques Used:
- Integration Testing: Component wiring across app/commands/receiver
- State Transition Testing: Lifespan initialise → teardown, registry adopt
- Decision Table Testing: Command dispatch (valid/invalid/unknown)
- Specification-based Testing: Factory contracts, response schemas
- Error Guessing: Invalid JSON, missing fields, unknown commands
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import cosalette
import pytest
from cosalette import AppContext, DeviceStore
from cosalette.stores import MemoryStore

import jeelink2mqtt.app as app_module
from jeelink2mqtt.adapters import FakeJeeLinkAdapter
from jeelink2mqtt.app import (
    SharedState,
    _build_sensor_configs,
    _lifespan,
    create_app,
    get_state,
)
from jeelink2mqtt.commands import register_commands
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.receiver import register_receiver
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from tests.fixtures.async_utils import wait_for_condition
from tests.fixtures.doubles import FakeDeviceContext

# ======================================================================
# Helpers
# ======================================================================


def _make_settings(
    *,
    sensor_names: list[str] | None = None,
    sensors: list[SensorConfigSettings] | None = None,
    staleness_timeout: float = 600.0,
) -> Jeelink2MqttSettings:
    """Build a Jeelink2MqttSettings for testing."""
    if sensors is None:
        names = sensor_names or ["office"]
        sensors = [SensorConfigSettings(name=n) for n in names]
    return Jeelink2MqttSettings(
        serial_port="/dev/ttyUSB0",
        staleness_timeout_seconds=staleness_timeout,
        median_filter_window=3,
        sensors=sensors,
    )


def _make_device_store(initial_data: dict | None = None) -> DeviceStore:
    """Create an in-memory DeviceStore for testing."""
    store_data = {"": initial_data} if initial_data else None
    backend = MemoryStore(initial=store_data)
    ds = DeviceStore(backend=backend, key="")
    ds.load()
    return ds


def _make_shared_state(
    configs: list[SensorConfig] | None = None,
    staleness_timeout: float = 600.0,
) -> SharedState:
    """Build a SharedState with a fresh registry and filter bank."""
    configs = configs or [SensorConfig(name="office")]
    return SharedState(
        registry=SensorRegistry(sensors=configs, staleness_timeout=staleness_timeout),
        filter_bank=FilterBank(window=3),
        sensor_configs={c.name: c for c in configs},
    )


def _extract_handler(app: cosalette.App, kind: str, name: str):
    """Extract a registered handler function from a cosalette App.

    Args:
        app: The cosalette App with registered handlers.
        kind: ``"command"`` or ``"device"``.
        name: The registration name to find.

    Returns:
        The handler's async function.
    """
    registry = app._commands if kind == "command" else app._devices
    for reg in registry:
        if reg.name == name:
            return reg.func
    msg = f"No {kind} named {name!r} found in app"
    raise LookupError(msg)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(autouse=True)
def _reset_app_state():
    """Ensure module-level _state is clean before and after each test.

    The lifespan and some tests mutate ``app_module._state`` directly;
    this fixture guarantees isolation.
    """
    app_module._state = None
    yield
    app_module._state = None


@pytest.fixture
def settings_one_sensor() -> Jeelink2MqttSettings:
    """Settings with a single 'office' sensor and small filter window."""
    return _make_settings(
        sensors=[SensorConfigSettings(name="office", temp_offset=-0.3)],
    )


@pytest.fixture
def settings_two_sensors() -> Jeelink2MqttSettings:
    """Settings with 'office' and 'outdoor' sensors."""
    return _make_settings(
        sensors=[
            SensorConfigSettings(name="office", temp_offset=-0.3, humidity_offset=1.0),
            SensorConfigSettings(name="outdoor"),
        ],
    )


# ======================================================================
# TestBuildSensorConfigs
# ======================================================================


@pytest.mark.integration
class TestBuildSensorConfigs:
    """Test _build_sensor_configs: settings → domain SensorConfig list.

    Technique: Specification-based — verify the mapping contract from
    settings-layer ``SensorConfigSettings`` to domain ``SensorConfig``.
    """

    def test_converts_sensors_with_offsets(
        self, settings_two_sensors: Jeelink2MqttSettings
    ) -> None:
        """Settings with offsets produce SensorConfig with matching values.

        Technique: Specification-based — field mapping fidelity.
        """
        # Arrange — settings_two_sensors has office(-0.3, 1.0) + outdoor(0, 0)

        # Act
        configs = _build_sensor_configs(settings_two_sensors)

        # Assert
        assert len(configs) == 2
        office = next(c for c in configs if c.name == "office")
        assert office.temp_offset == -0.3
        assert office.humidity_offset == 1.0
        outdoor = next(c for c in configs if c.name == "outdoor")
        assert outdoor.temp_offset == 0.0
        assert outdoor.humidity_offset == 0.0

    def test_empty_sensors_produces_empty_list(self) -> None:
        """Settings with no sensors yield an empty config list.

        Technique: Boundary Value Analysis — zero-element input.
        """
        # Arrange
        settings = _make_settings(sensors=[])

        # Act
        configs = _build_sensor_configs(settings)

        # Assert
        assert configs == []

    def test_staleness_timeout_propagated(self) -> None:
        """Per-sensor staleness override is included in SensorConfig.

        Technique: Specification-based — optional field propagation.
        """
        # Arrange
        settings = _make_settings(
            sensors=[SensorConfigSettings(name="garage", staleness_timeout=120.0)],
        )

        # Act
        configs = _build_sensor_configs(settings)

        # Assert
        assert len(configs) == 1
        assert configs[0].staleness_timeout == 120.0


# ======================================================================
# TestLifespan
# ======================================================================


@pytest.mark.integration
class TestLifespan:
    """Test _lifespan: async context manager for shared state lifecycle.

    Technique: State Transition Testing — uninitialised → active → torn down.
    """

    async def test_lifespan_initialises_state(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Entering the lifespan sets module-level _state with domain objects.

        Technique: State Transition — None → SharedState.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})

        # Act
        async with _lifespan(ctx):
            state = get_state()

            # Assert — state is populated
            assert isinstance(state, SharedState)
            assert isinstance(state.registry, SensorRegistry)
            assert isinstance(state.filter_bank, FilterBank)
            assert "office" in state.sensor_configs

    async def test_lifespan_tears_down_state(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Exiting the lifespan resets _state to None.

        Technique: State Transition — SharedState → None.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})

        # Act
        async with _lifespan(ctx):
            pass  # lifespan active, _state is set

        # Assert — after exit, state is torn down
        assert app_module._state is None
        with pytest.raises(RuntimeError, match="not initialised"):
            get_state()

    async def test_lifespan_sensor_config_lookup(
        self, settings_two_sensors: Jeelink2MqttSettings
    ) -> None:
        """Lifespan builds sensor_configs dict keyed by name.

        Technique: Specification-based — lookup table construction.
        """
        # Arrange
        ctx = AppContext(settings=settings_two_sensors, adapters={})

        # Act
        async with _lifespan(ctx):
            state = get_state()

            # Assert
            assert set(state.sensor_configs.keys()) == {"office", "outdoor"}
            assert state.sensor_configs["office"].temp_offset == -0.3


# ======================================================================
# TestCreateApp
# ======================================================================


@pytest.mark.integration
class TestCreateApp:
    """Test create_app: composition root producing a cosalette App.

    Technique: Specification-based — factory contract verification.
    """

    def test_returns_cosalette_app(self) -> None:
        """create_app() returns a cosalette.App instance.

        Technique: Specification-based — return type contract.
        """
        # Arrange / Act
        app = create_app()

        # Assert
        assert isinstance(app, cosalette.App)

    def test_app_has_correct_name(self) -> None:
        """The App is named 'jeelink2mqtt'.

        Technique: Specification-based — identity attribute.
        """
        # Arrange / Act
        app = create_app()

        # Assert
        assert app._name == "jeelink2mqtt"

    def test_app_registers_receiver_and_commands(self) -> None:
        """create_app() registers both the receiver device and mapping command.

        Technique: Integration Testing — wiring completeness.
        """
        # Arrange / Act
        app = create_app()

        # Assert — at least one device and one command registered
        assert len(app._devices) >= 1
        assert len(app._commands) >= 1
        device_names = [d.name for d in app._devices]
        command_names = [c.name for c in app._commands]
        assert "receiver" in device_names
        assert "mapping" in command_names


# ======================================================================
# TestHandleMappingDispatch
# ======================================================================


@pytest.mark.integration
class TestHandleMappingDispatch:
    """Test the handle_mapping wrapper registered via @app.command.

    Exercises the command dispatch code in commands.py lines 52-100:
    JSON parsing, handler routing, store persistence, error responses.

    Technique: Decision Table Testing — command × validity → response.
    """

    @pytest.fixture
    def _wired_state(self) -> SharedState:
        """Set up module-level _state so get_state() works inside the handler."""
        state = _make_shared_state(
            configs=[
                SensorConfig(name="office"),
                SensorConfig(name="outdoor"),
            ],
        )
        app_module._state = state
        return state

    @pytest.fixture
    def handle_mapping(self):
        """Extract the registered handle_mapping function from a fresh App."""
        app = cosalette.App(name="test", version="0.0.0")
        register_commands(app)
        return _extract_handler(app, "command", "mapping")

    async def test_invalid_json_returns_error(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """Non-JSON payload yields an error dict.

        Technique: Error Guessing — malformed input.
        """
        # Arrange
        store = _make_device_store()

        # Act
        result = await handle_mapping(payload="not-json{{{", store=store)

        # Assert
        assert result == {"error": "Invalid JSON payload"}

    async def test_unknown_command_returns_error(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """Payload with unrecognised command yields an error dict.

        Technique: Decision Table — unknown command branch.
        """
        # Arrange
        store = _make_device_store()
        payload = json.dumps({"command": "explode"})

        # Act
        result = await handle_mapping(payload=payload, store=store)

        # Assert
        assert result == {"error": "Unknown command: explode"}

    async def test_empty_command_returns_error(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """Payload with no 'command' key yields an error for empty string.

        Technique: Error Guessing — missing required field.
        """
        # Arrange
        store = _make_device_store()
        payload = json.dumps({"not_command": "assign"})

        # Act
        result = await handle_mapping(payload=payload, store=store)

        # Assert
        assert "error" in result
        assert "Unknown command" in str(result["error"])

    async def test_assign_returns_ok_and_persists(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """Valid assign command creates mapping and persists to store.

        Technique: Decision Table — assign → ok + store write.
        """
        # Arrange
        store = _make_device_store()
        payload = json.dumps(
            {
                "command": "assign",
                "sensor_name": "office",
                "sensor_id": 42,
            }
        )

        # Act
        result = await handle_mapping(payload=payload, store=store)

        # Assert — response
        assert result["status"] == "ok"
        assert result["event"]["event_type"] == "manual_assign"
        assert result["event"]["sensor_name"] == "office"
        assert result["event"]["new_sensor_id"] == 42

        # Assert — persistence
        assert "registry" in store
        assert _wired_state.registry.resolve(42) == "office"

    async def test_reset_returns_ok_and_persists(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """Reset removes an existing mapping and persists the change.

        Technique: State Transition — mapped → unmapped.
        """
        # Arrange — first assign, then reset
        store = _make_device_store()
        assign_payload = json.dumps(
            {
                "command": "assign",
                "sensor_name": "office",
                "sensor_id": 42,
            }
        )
        await handle_mapping(payload=assign_payload, store=store)

        reset_payload = json.dumps(
            {
                "command": "reset",
                "sensor_name": "office",
            }
        )

        # Act
        result = await handle_mapping(payload=reset_payload, store=store)

        # Assert
        assert result["status"] == "ok"
        assert result["event"]["sensor_name"] == "office"
        assert _wired_state.registry.resolve(42) is None

    async def test_reset_all_clears_all_mappings(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """reset_all removes every mapping and persists.

        Technique: Decision Table — reset_all → cleared count.
        """
        # Arrange — assign two sensors
        store = _make_device_store()
        for name, sid in [("office", 42), ("outdoor", 99)]:
            payload = json.dumps(
                {
                    "command": "assign",
                    "sensor_name": name,
                    "sensor_id": sid,
                }
            )
            await handle_mapping(payload=payload, store=store)

        # Act
        result = await handle_mapping(
            payload=json.dumps({"command": "reset_all"}),
            store=store,
        )

        # Assert
        assert result["status"] == "ok"
        assert result["cleared"] == 2

    async def test_list_unknown_returns_unmapped_ids(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """list_unknown returns recently-seen unmapped sensor IDs.

        Technique: Decision Table — list_unknown → read-only query.
        """
        # Arrange — inject an unmapped reading into the registry
        reading = SensorReading(
            sensor_id=999,
            temperature=20.0,
            humidity=50,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )
        # Assign both sensors so 999 is truly unknown
        _wired_state.registry.assign("office", 42)
        _wired_state.registry.assign("outdoor", 77)
        _wired_state.registry.record_reading(reading)

        store = _make_device_store()
        payload = json.dumps({"command": "list_unknown"})

        # Act
        result = await handle_mapping(payload=payload, store=store)

        # Assert
        assert result["status"] == "ok"
        assert "999" in result["unknown_sensors"]

    async def test_list_unknown_does_not_persist(
        self, handle_mapping, _wired_state: SharedState
    ) -> None:
        """list_unknown is read-only — store is NOT written.

        Technique: Specification-based — mutation vs. query contract.
        """
        # Arrange
        store = _make_device_store()
        payload = json.dumps({"command": "list_unknown"})

        # Act
        await handle_mapping(payload=payload, store=store)

        # Assert — store was not written to
        assert "registry" not in store


# ======================================================================
# TestReceiverMainLoop
# ======================================================================


@pytest.mark.integration
class TestReceiverMainLoop:
    """Test the receiver device function registered via @app.device.

    Exercises receiver.py lines 45-146: adapter lifecycle, queue bridge,
    read loop, pipeline processing, publish, and shutdown.

    Technique: Integration Testing — adapter → queue → pipeline → publish.
    """

    @pytest.fixture
    def receiver_fn(self):
        """Extract the registered receiver function from a fresh App."""
        app = cosalette.App(name="test", version="0.0.0")
        register_receiver(app)
        return _extract_handler(app, "device", "receiver")

    @pytest.fixture
    def wired_state_one_sensor(self) -> SharedState:
        """Set up module-level _state with 'office' sensor."""
        configs = [SensorConfig(name="office", temp_offset=-0.3)]
        state = SharedState(
            registry=SensorRegistry(sensors=configs, staleness_timeout=600.0),
            filter_bank=FilterBank(window=3),
            sensor_configs={c.name: c for c in configs},
        )
        app_module._state = state
        return state

    async def test_receiver_publishes_raw_on_reading(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Injected reading triggers a raw/state publish.

        Technique: Integration Testing — adapter → queue → raw publish.
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        # Act — run receiver as a background task
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        # Inject a reading through the adapter's callback bridge
        adapter.inject(reading)
        await wait_for_condition(
            lambda: any(t == "raw/state" for t, _, _ in ctx.published),
            description="raw/state published",
        )

        # Signal shutdown and wait for clean exit
        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — raw/state must appear in published messages
        raw_topics = [t for t, _p, _r in ctx.published if t == "raw/state"]
        assert len(raw_topics) >= 1

        # Verify the raw payload contains the sensor_id
        raw_payloads = [json.loads(p) for t, p, _r in ctx.published if t == "raw/state"]
        assert any(payload["sensor_id"] == 42 for payload in raw_payloads)

    async def test_receiver_auto_adopts_and_publishes_sensor_state(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """With one unmapped sensor, auto-adopt triggers and sensor state
        is published after enough readings fill the filter window.

        Technique: State Transition — unmapped → auto-adopted → published.
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        # Act — run receiver and inject enough readings for filter convergence
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        # Inject 3 readings (window=3 for filter convergence)
        for _ in range(3):
            adapter.inject(reading)
        await wait_for_condition(
            lambda: any(t == "office/state" for t, _, _ in ctx.published),
            description="sensor state published",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — sensor state published under office/state
        sensor_topics = [t for t, _p, _r in ctx.published if t == "office/state"]
        assert len(sensor_topics) >= 1

        # Verify calibrated temperature includes the -0.3 offset
        sensor_payloads = [
            json.loads(p) for t, p, _r in ctx.published if t == "office/state"
        ]
        assert any(
            payload["temperature"] == pytest.approx(21.2, abs=0.01)
            for payload in sensor_payloads
        )

    async def test_receiver_publishes_mapping_events_on_adopt(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Auto-adopt triggers mapping/event and mapping/state publishes.

        Technique: Integration Testing — registry event → MQTT publish.
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        # Act
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        adapter.inject(reading)
        await wait_for_condition(
            lambda: any(t == "mapping/event" for t, _, _ in ctx.published),
            description="mapping event published",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — mapping event published
        event_topics = [t for t, _p, _r in ctx.published if t == "mapping/event"]
        assert len(event_topics) >= 1

        event_payloads = [
            json.loads(p) for t, p, _r in ctx.published if t == "mapping/event"
        ]
        assert any(
            e["event_type"] == "auto_adopt" and e["sensor_name"] == "office"
            for e in event_payloads
        )

        # Assert — mapping state snapshot published
        state_topics = [t for t, _p, _r in ctx.published if t == "mapping/state"]
        assert len(state_topics) >= 1

    async def test_receiver_persists_registry_on_mapping_change(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Registry state is persisted to the device store after mapping changes.

        Technique: Specification-based — persistence contract (ADR-004).
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        # Act
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        adapter.inject(reading)
        await wait_for_condition(
            lambda: "registry" in store,
            description="registry persisted",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — store contains persisted registry
        assert "registry" in store

    async def test_receiver_publishes_availability_on_reading(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Mapped sensor gets 'online' availability after a reading.

        Technique: Specification-based — availability contract.
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()
        reading = SensorReading(
            sensor_id=42,
            temperature=21.5,
            humidity=55,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        # Act
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        # Fill filter window
        for _ in range(3):
            adapter.inject(reading)
        await wait_for_condition(
            lambda: any(
                t == "office/availability" and p == "online"
                for t, p, _ in ctx.published
            ),
            description="online availability published",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — online availability published (retained)
        online_msgs = [
            (t, p, r) for t, p, r in ctx.published if t == "office/availability"
        ]
        # Should have at least one 'online' (from reading) and one 'offline' (shutdown)
        payloads = [p for _t, p, _r in online_msgs]
        assert "online" in payloads
        # Last availability message should be 'offline' (shutdown cleanup)
        assert online_msgs[-1][1] == "offline"

    async def test_receiver_publishes_offline_on_shutdown(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """All configured sensors go 'offline' on receiver shutdown.

        Technique: State Transition — running → shutdown → offline.
        """
        # Arrange
        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()
        store = _make_device_store()

        # Act — start and immediately shut down (no readings)
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — offline published for configured sensor
        offline_msgs = [
            (t, p)
            for t, p, _r in ctx.published
            if t == "office/availability" and p == "offline"
        ]
        assert len(offline_msgs) >= 1

    async def test_receiver_restores_persisted_registry(
        self,
        receiver_fn,
        wired_state_one_sensor: SharedState,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Receiver restores registry from device store on startup.

        Technique: Specification-based — persistence round-trip (ADR-004).
        """
        # Arrange — pre-populate store with a persisted registry
        configs = [SensorConfig(name="office", temp_offset=-0.3)]
        pre_registry = SensorRegistry(sensors=configs, staleness_timeout=600.0)
        pre_registry.assign("office", 77)
        pre_registry.drain_events()  # Clear events from assign
        initial_data = {"registry": pre_registry.to_dict()}
        store = _make_device_store(initial_data)

        ctx = FakeDeviceContext()
        adapter = FakeJeeLinkAdapter()

        # Act — run receiver; it should restore the mapping
        task = asyncio.create_task(
            receiver_fn(ctx, adapter, store, settings_one_sensor)
        )
        await wait_for_condition(
            lambda: adapter._callback is not None,
            description="adapter callback registered",
        )

        # Inject a reading with the persisted sensor_id
        reading = SensorReading(
            sensor_id=77,
            temperature=22.0,
            humidity=60,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )
        for _ in range(3):
            adapter.inject(reading)
        await wait_for_condition(
            lambda: any(t == "office/state" for t, _, _ in ctx.published),
            description="sensor state published",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — sensor state published under office (restored mapping)
        sensor_topics = [t for t, _p, _r in ctx.published if t == "office/state"]
        assert len(sensor_topics) >= 1
