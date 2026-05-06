"""Integration tests for the jeelink2mqtt application layer.

Tests the cosalette application wiring: ``app.py`` (lifespan,
sensor config builder), ``commands.py`` (mapping command
implementations), and ``receiver.py`` (pipeline helpers / main loop).

These tests exercise the *registered* handlers extracted from the
module-level ``app`` in ``main.py``, verifying that the declarative
wiring works end-to-end with real domain objects and in-memory doubles.

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
from typing import TYPE_CHECKING

import cosalette
import pytest
from cosalette import AppContext, DeviceStore
from cosalette.stores import MemoryStore

from jeelink2mqtt.adapters import FakeJeeLinkAdapter
from jeelink2mqtt.app import _lifespan
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.main import app
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings, SensorConfigSettings
from jeelink2mqtt.state import (
    SharedState,
    _build_sensor_configs,
    build_shared_state,
)
from tests.fixtures.async_utils import wait_for_condition
from tests.fixtures.doubles import FakeDeviceContext

if TYPE_CHECKING:
    from cosalette import MockMqttClient

# ======================================================================
# Helpers
# ======================================================================


def _build_integration_app() -> cosalette.App:
    """Create a test app with minimal components for mapping framework tests.

    Only includes mapping sub-commands and shared state factory.
    Avoids unnecessary background loops for command routing tests.
    """
    from cosalette.stores import MemoryStore

    from jeelink2mqtt import __version__
    from jeelink2mqtt.main import (
        mapping_assign,
        mapping_list_unknown,
        mapping_reset,
        mapping_reset_all,
    )

    test_app = cosalette.App(
        name="jeelink2mqtt",
        version=__version__,
        description="JeeLink LaCrosse sensor bridge for MQTT",
        settings_class=Jeelink2MqttSettings,
        store=MemoryStore(),
    )

    # Register the same state factory as the real app
    @test_app.state
    def shared_state(settings: Jeelink2MqttSettings) -> SharedState:
        return build_shared_state(settings)

    # Register mapping sub-commands
    test_app.command(
        "mapping",
        sub="assign",
        summary="Manually assign an ephemeral sensor ID to a logical name",
    )(mapping_assign)
    test_app.command(
        "mapping", sub="reset", summary="Remove the mapping for a named sensor"
    )(mapping_reset)
    test_app.command("mapping", sub="reset_all", summary="Clear all sensor mappings")(
        mapping_reset_all
    )
    test_app.command(
        "mapping",
        sub="list_unknown",
        summary="Return recently-seen sensor IDs that are not yet mapped",
    )(mapping_list_unknown)

    return test_app


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


def _extract_handler(app: cosalette.App, kind: str, name: str, sub: str | None = None):
    """Extract a registered handler function from a cosalette App.

    Args:
        app: The cosalette App with registered handlers.
        kind: ``"command"`` or ``"device"``.
        name: The registration name to find.
        sub: The sub-command name (for sub-commands only).

    Returns:
        The handler's async function.
    """
    registry = app._commands if kind == "command" else app._devices
    for reg in registry:
        if reg.name == name:
            if sub is None:
                # Looking for a handler without sub-command
                if getattr(reg, "sub", None) is None:
                    return reg.func
            else:
                # Looking for a specific sub-command handler
                if getattr(reg, "sub", None) == sub:
                    return reg.func

    sub_desc = f" (sub={sub!r})" if sub else ""
    msg = f"No {kind} named {name!r}{sub_desc} found in app"
    raise LookupError(msg)


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(autouse=True)
def _reset_app_state():
    """No-op fixture retained for compatibility; state is lifespan-managed."""
    yield


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
# TestBuildSharedState
# ======================================================================


@pytest.mark.integration
class TestBuildSharedState:
    """Test build_shared_state: factory function for @app.state decorator.

    Technique: Specification-based — verify the factory contract.
    """

    def test_builds_shared_state_with_registry(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Factory produces SharedState with populated registry and filter bank.

        Technique: Specification-based — domain object assembly.
        """
        # Act
        state = build_shared_state(settings_one_sensor)

        # Assert
        assert isinstance(state, SharedState)
        assert isinstance(state.registry, SensorRegistry)
        assert isinstance(state.filter_bank, FilterBank)
        assert "office" in state.sensor_configs

    def test_builds_empty_state_for_no_sensors(self) -> None:
        """Factory handles settings with no sensors.

        Technique: Boundary Value Analysis — zero sensors.
        """
        # Arrange
        settings = _make_settings(sensors=[])

        # Act
        state = build_shared_state(settings)

        # Assert
        assert isinstance(state, SharedState)
        assert len(state.sensor_configs) == 0
        assert isinstance(state.registry, SensorRegistry)
        assert isinstance(state.filter_bank, FilterBank)


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
        async with _lifespan(ctx) as state:
            # Assert — state is populated
            assert isinstance(state, SharedState)
            assert isinstance(state.registry, SensorRegistry)
            assert isinstance(state.filter_bank, FilterBank)
            assert "office" in state.sensor_configs

    async def test_lifespan_tears_down_state(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Exiting the lifespan completes normally.

        Technique: State Transition — SharedState → cleanup.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})

        # Act & Assert — lifespan completes without error
        async with _lifespan(ctx) as state:
            assert isinstance(state, SharedState)
        # After context exit, lifespan has completed

    async def test_lifespan_sensor_config_lookup(
        self, settings_two_sensors: Jeelink2MqttSettings
    ) -> None:
        """Lifespan builds sensor_configs dict keyed by name.

        Technique: Specification-based — lookup table construction.
        """
        # Arrange
        ctx = AppContext(settings=settings_two_sensors, adapters={})

        # Act
        async with _lifespan(ctx) as state:
            # Assert
            assert set(state.sensor_configs.keys()) == {"office", "outdoor"}
            assert state.sensor_configs["office"].temp_offset == -0.3


# ======================================================================
# TestCreateApp
# ======================================================================


@pytest.mark.integration
class TestApp:
    """Test the module-level app: composition root producing a cosalette App.

    Technique: Specification-based — factory contract verification.
    """

    def test_returns_cosalette_app(self) -> None:
        """app is a cosalette.App instance.

        Technique: Specification-based — return type contract.
        """
        assert isinstance(app, cosalette.App)

    def test_app_has_correct_name(self) -> None:
        """The App is named 'jeelink2mqtt'.

        Technique: Specification-based — identity attribute.
        """
        assert app._name == "jeelink2mqtt"

    def test_app_uses_state_factories(self) -> None:
        """The App uses @app.state decorator, not lifespan.

        Technique: Specification-based — verifies the cosalette 0.3.13 refactor.
        """
        # Check that the app has state factories registered
        assert hasattr(app, "_state_factories")
        assert len(app._state_factories) > 0

        # Find the SharedState factory
        shared_state_factory = None
        for factory in app._state_factories:
            if hasattr(factory.factory, "__annotations__"):
                return_annotation = factory.factory.__annotations__.get("return")
                # Handle both string annotation and class annotation
                if (
                    return_annotation == SharedState
                    or return_annotation == "SharedState"
                ):
                    shared_state_factory = factory
                    break

        assert shared_state_factory is not None, "No SharedState factory found"
        assert shared_state_factory.factory.__name__ == "shared_state"

    def test_app_registers_receiver_and_commands(self) -> None:
        """app registers both the receiver device and mapping command.

        Technique: Integration Testing — wiring completeness.
        """
        assert len(app._devices) >= 1
        assert len(app._commands) >= 1
        device_names = [d.name for d in app._devices]
        command_names = [c.name for c in app._commands]
        assert "receiver" in device_names
        assert "mapping" in command_names

    def test_app_registers_periodic_handlers(self) -> None:
        """app registers staleness and heartbeat timing handlers.

        Technique: Specification-based — verify cap-i4l refactor wiring.
        Ensures staleness_checker and heartbeat_publisher are registered
        as named device handlers.
        """
        device_names = [d.name for d in app._devices]
        assert "staleness" in device_names, "staleness handler not registered"
        assert "heartbeat" in device_names, "heartbeat handler not registered"

    def test_shared_state_has_heartbeat_state(self) -> None:
        """SharedState includes last_readings, last_publish_time, and last_availability.

        Technique: Specification-based — verify heartbeat and dedup state exists.
        Ensures the SharedState dataclass has the required fields for
        heartbeat tracking and duplicate offline-publish prevention.
        """
        settings = _make_settings(sensor_names=["office"])
        state = build_shared_state(settings)

        assert isinstance(state.last_readings, dict)
        assert isinstance(state.last_publish_time, dict)
        assert isinstance(state.last_availability, dict)


# ======================================================================
# TestHandleMappingDispatch
# ======================================================================


@pytest.mark.integration
class TestMappingSubCommands:
    """Test the mapping sub-command handlers registered via @app.command.

    Exercises the sub-command dispatch and individual command handlers in main.py:
    JSON parsing, handler routing, store persistence, error responses.

    Technique: Decision Table Testing — sub-command × validity → response.
    """

    async def test_handle_mapping_with_state(
        self,
        mapping_list_unknown,
        settings_one_sensor: Jeelink2MqttSettings,
    ) -> None:
        """Test command handler with proper state injection.

        Technique: Integration Testing — lifespan + command handler.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()
        payload = json.dumps({"command": "list_unknown"})

        async with _lifespan(ctx) as state:
            # Act
            result = await mapping_list_unknown(
                payload=payload, store=store, state=state
            )

            # Assert
            assert result is not None
            assert result["status"] == "ok"
            assert "unknown_sensors" in result

    @pytest.fixture
    def mapping_assign(self):
        """Extract the registered mapping_assign function from the app."""
        return _extract_handler(app, "command", "mapping", sub="assign")

    @pytest.fixture
    def mapping_reset(self):
        """Extract the registered mapping_reset function from the app."""
        return _extract_handler(app, "command", "mapping", sub="reset")

    @pytest.fixture
    def mapping_reset_all(self):
        """Extract the registered mapping_reset_all function from the app."""
        return _extract_handler(app, "command", "mapping", sub="reset_all")

    @pytest.fixture
    def mapping_list_unknown(self):
        """Extract the registered mapping_list_unknown function from the app."""
        return _extract_handler(app, "command", "mapping", sub="list_unknown")

    async def test_invalid_json_returns_error(
        self, mapping_assign, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Non-JSON payload yields an error dict.

        Technique: Error Guessing — malformed input.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()

        async with _lifespan(ctx) as state:
            # Act
            result = await mapping_assign(
                payload="not-json{{{{", store=store, state=state
            )

            # Assert
            assert result == {"error": "Invalid JSON payload"}

    @pytest.mark.parametrize("payload", ["[]", '"mapping"', "42"])
    async def test_non_object_json_returns_error(
        self,
        mapping_assign,
        settings_one_sensor: Jeelink2MqttSettings,
        payload: str,
    ) -> None:
        """Valid JSON that is not an object yields an error dict.

        Technique: Equivalence Partitioning — JSON scalar/array inputs.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()

        async with _lifespan(ctx) as state:
            # Act
            result = await mapping_assign(payload=payload, store=store, state=state)

            # Assert
            assert result == {"error": "JSON payload must be an object"}

    async def test_app_has_mapping_subcommand_registrations(self) -> None:
        """Verify that all expected mapping sub-commands are registered.

        Technique: Specification-based — declarative registrations.
        """
        # Find all mapping command registrations
        mapping_commands = [
            reg
            for reg in app._commands
            if reg.name == "mapping" and hasattr(reg, "sub")
        ]

        # Extract sub-command names
        sub_commands = {reg.sub for reg in mapping_commands}

        # Assert all expected sub-commands are registered
        expected = {"assign", "reset", "reset_all", "list_unknown"}
        assert sub_commands == expected

        # Verify each has a distinct handler function
        handlers = {reg.sub: reg.func for reg in mapping_commands}
        assert len(handlers) == len(expected)  # No duplicates

    async def test_assign_returns_ok_and_persists(
        self, mapping_assign, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Valid assign command creates mapping and persists to store.

        Technique: Decision Table — assign → ok + store write.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()
        payload = json.dumps(
            {
                "command": "assign",
                "sensor_name": "office",
                "sensor_id": 42,
            }
        )

        async with _lifespan(ctx) as state:
            # Act
            result = await mapping_assign(payload=payload, store=store, state=state)

            # Assert — response
            assert result["status"] == "ok"
            assert result["event"]["event_type"] == "manual_assign"
            assert result["event"]["sensor_name"] == "office"
            assert result["event"]["new_sensor_id"] == 42

            # Assert — persistence
            assert "registry" in store
            assert state.registry.resolve(42) == "office"

    async def test_assign_payload_with_error_metadata_key_succeeds(
        self, mapping_assign, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Valid assign payload containing "error" key as metadata is processed correctly.

        Technique: Regression Testing — prevents control flow misinterpretation
        of "error" in valid payload data vs. actual error conditions.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()
        payload = json.dumps(
            {
                "command": "assign",
                "sensor_name": "office",
                "sensor_id": 42,
                "error": "metadata",
            }
        )

        async with _lifespan(ctx) as state:
            # Act
            result = await mapping_assign(payload=payload, store=store, state=state)

            # Assert — response
            assert result["status"] == "ok"
            assert result["event"]["new_sensor_id"] == 42

            # Assert — persistence and state
            assert state.registry.resolve(42) == "office"
            assert "registry" in store

    async def test_reset_returns_ok_and_persists(
        self, mapping_assign, mapping_reset, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Reset removes an existing mapping and persists the change.

        Technique: State Transition — mapped → unmapped.
        """
        # Arrange — first assign, then reset
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()
        assign_payload = json.dumps(
            {
                "command": "assign",
                "sensor_name": "office",
                "sensor_id": 42,
            }
        )

        async with _lifespan(ctx) as state:
            await mapping_assign(payload=assign_payload, store=store, state=state)

            reset_payload = json.dumps(
                {
                    "command": "reset",
                    "sensor_name": "office",
                }
            )

            # Act
            result = await mapping_reset(
                payload=reset_payload, store=store, state=state
            )

            # Assert
            assert result["status"] == "ok"
            assert result["event"]["sensor_name"] == "office"
            assert state.registry.resolve(42) is None

    async def test_reset_all_clears_all_mappings(
        self,
        mapping_assign,
        mapping_reset_all,
        settings_two_sensors: Jeelink2MqttSettings,
    ) -> None:
        """reset_all removes every mapping and persists.

        Technique: Decision Table — reset_all → cleared count.
        """
        # Arrange — assign two sensors
        ctx = AppContext(settings=settings_two_sensors, adapters={})
        store = _make_device_store()

        async with _lifespan(ctx) as state:
            for name, sid in [("office", 42), ("outdoor", 99)]:
                payload = json.dumps(
                    {
                        "command": "assign",
                        "sensor_name": name,
                        "sensor_id": sid,
                    }
                )
                result = await mapping_assign(payload=payload, store=store, state=state)
                assert result["status"] == "ok", f"assign {name} failed: {result}"

            # Act
            result = await mapping_reset_all(
                payload=json.dumps({"command": "reset_all"}),
                store=store,
                state=state,
            )

            # Assert
            assert result["status"] == "ok"
            assert result["cleared"] == 2

    async def test_list_unknown_returns_unmapped_ids(
        self, mapping_list_unknown, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """list_unknown returns recently-seen unmapped sensor IDs.

        Technique: Decision Table — list_unknown → read-only query.
        """
        # Arrange — inject an unmapped reading into the registry
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        reading = SensorReading(
            sensor_id=999,
            temperature=20.0,
            humidity=50,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )

        async with _lifespan(ctx) as state:
            # Assign both sensors so 999 is truly unknown
            state.registry.assign("office", 42)
            state.registry.record_reading(reading)

            store = _make_device_store()
            payload = json.dumps({"command": "list_unknown"})

            # Act
            result = await mapping_list_unknown(
                payload=payload, store=store, state=state
            )

            # Assert
            assert result["status"] == "ok"
            assert "999" in result["unknown_sensors"]

    async def test_list_unknown_does_not_persist(
        self, mapping_list_unknown, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """list_unknown is read-only — store is NOT written.

        Technique: Specification-based — mutation vs. query contract.
        """
        # Arrange
        ctx = AppContext(settings=settings_one_sensor, adapters={})
        store = _make_device_store()
        payload = json.dumps({"command": "list_unknown"})

        async with _lifespan(ctx) as state:
            # Act
            await mapping_list_unknown(payload=payload, store=store, state=state)

            # Assert — no persistence occurred
            assert len(store) == 0
        assert "registry" not in store


# ======================================================================
# TestMappingSubCommandErrors
# ======================================================================


async def _run_mapping_command(
    payload: str, settings: Jeelink2MqttSettings, expected_topic: str
) -> MockMqttClient:
    """Helper to run a mapping command and return the MockMqttClient after completion.

    Handles app startup, subscription wait, command delivery, response wait,
    and shutdown. Returns the MockMqttClient for assertion checking.

    Args:
        payload: The command payload to deliver to jeelink2mqtt/mapping/set
        settings: App settings
        expected_topic: Topic to wait for (e.g., 'jeelink2mqtt/mapping/error' or 'jeelink2mqtt/mapping/state')

    Returns:
        MockMqttClient instance with published messages available for assertions
    """
    from cosalette import MockMqttClient

    mock_mqtt = MockMqttClient()
    test_app = _build_integration_app()

    shutdown_event = asyncio.Event()
    task = asyncio.create_task(
        test_app._run_async(
            mqtt=mock_mqtt,
            settings=settings,
            shutdown_event=shutdown_event,
        )
    )

    try:
        # Wait for mapping subscription to be present
        await wait_for_condition(
            lambda: (
                "jeelink2mqtt/mapping/set" in getattr(mock_mqtt, "subscriptions", set())
            ),
            timeout=1.0,
            description="mapping subscription setup",
        )

        # Deliver command payload
        await mock_mqtt.deliver("jeelink2mqtt/mapping/set", payload)

        # Wait for expected response topic to have at least one publish
        await wait_for_condition(
            lambda: any(
                topic == expected_topic
                for topic, _payload, _retain, _qos in mock_mqtt.published
            ),
            timeout=1.0,
            description=f"{expected_topic} message publication",
        )

    finally:
        # Shutdown
        shutdown_event.set()
        await task

    return mock_mqtt


@pytest.mark.integration
class TestMappingSubCommandErrors:
    """Test sub-command error handling through the real cosalette framework.

    These tests exercise the cosalette CommandRunner.register_sub_command_proxy
    dispatch path, not direct handler calls. Uses MockMqttClient.deliver() to
    trigger the real app error handling and verify structured error responses.

    Technique: Framework Integration Testing — cosalette sub-dispatch errors.
    """

    async def test_invalid_json_publishes_structured_error(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Invalid JSON to mapping/set publishes error_type='invalid_json'.

        Technique: Error Guessing — malformed JSON input through framework.
        """
        # Act
        mock_mqtt = await _run_mapping_command(
            "not-json{{{{", settings_one_sensor, "jeelink2mqtt/mapping/error"
        )

        # Assert — structured error published to mapping/error
        error_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/error"
        ]
        assert len(error_msgs) >= 1

        error_data = json.loads(error_msgs[0])
        assert error_data["error_type"] == "invalid_json"
        assert "message" in error_data
        assert "device" in error_data
        assert "timestamp" in error_data

        # Assert — no mapping/state response for errors
        mapping_state_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/state"
        ]
        # Should not have mapping/state triggered by this error
        assert len(mapping_state_msgs) == 0

    async def test_missing_command_field_publishes_structured_error(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Missing 'command' field publishes error_type='missing_sub_key'.

        Technique: Error Guessing — missing required field through framework.
        """
        # Act
        mock_mqtt = await _run_mapping_command(
            json.dumps({"sensor_name": "office", "sensor_id": 42}),
            settings_one_sensor,
            "jeelink2mqtt/mapping/error",
        )

        # Assert — structured error published
        error_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/error"
        ]
        assert len(error_msgs) >= 1

        error_data = json.loads(error_msgs[0])
        assert error_data["error_type"] == "missing_sub_key"
        assert "command" in error_data["message"]

        # Assert — no mapping/state response for errors
        mapping_state_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/state"
        ]
        assert len(mapping_state_msgs) == 0

    async def test_unknown_command_publishes_structured_error(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Unknown command like 'explode' publishes error_type='unknown_sub_command'.

        Technique: Error Guessing — unknown sub-command through framework.
        """
        # Act
        mock_mqtt = await _run_mapping_command(
            json.dumps({"command": "explode", "data": "boom"}),
            settings_one_sensor,
            "jeelink2mqtt/mapping/error",
        )

        # Assert — structured error published
        error_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/error"
        ]
        assert len(error_msgs) >= 1

        error_data = json.loads(error_msgs[0])
        assert error_data["error_type"] == "unknown_sub_command"
        assert "explode" in error_data["message"]

        # Assert — no mapping/state response for errors
        mapping_state_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/state"
        ]
        assert len(mapping_state_msgs) == 0

    async def test_valid_command_does_publish_mapping_state(
        self, settings_one_sensor: Jeelink2MqttSettings
    ) -> None:
        """Valid command publishes mapping/state response (contrast to errors).

        Technique: Specification-based — positive case for comparison.
        """
        # Act
        mock_mqtt = await _run_mapping_command(
            json.dumps({"command": "assign", "sensor_name": "office", "sensor_id": 42}),
            settings_one_sensor,
            "jeelink2mqtt/mapping/state",
        )

        # Assert — mapping/state response published for valid commands
        mapping_state_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/state"
        ]
        assert len(mapping_state_msgs) >= 1

        # Should be valid command response
        state_data = json.loads(mapping_state_msgs[0])
        assert state_data["status"] == "ok"

        # Assert — no error messages for valid commands
        error_msgs = [
            payload
            for topic, payload, _retain, _qos in mock_mqtt.published
            if topic == "jeelink2mqtt/mapping/error"
        ]
        assert len(error_msgs) == 0


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
        """Extract the registered receiver function from the app."""
        return _extract_handler(app, "device", "receiver")

    @pytest.fixture
    def wired_state_one_sensor(self) -> SharedState:
        """Build a SharedState with 'office' sensor for injection."""
        configs = [SensorConfig(name="office", temp_offset=-0.3)]
        return SharedState(
            registry=SensorRegistry(sensors=configs, staleness_timeout=600.0),
            filter_bank=FilterBank(window=3),
            sensor_configs={c.name: c for c in configs},
        )

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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
        )

        # Inject a reading through the adapter's async iterator
        adapter.inject_async(reading)
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
        )

        # Inject 3 readings (window=3 for filter convergence)
        for _ in range(3):
            adapter.inject_async(reading)
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
        )

        adapter.inject_async(reading)
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
        )

        adapter.inject_async(reading)
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
        )

        # Fill filter window
        for _ in range(3):
            adapter.inject_async(reading)
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
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
            receiver_fn(
                ctx, adapter, store, settings_one_sensor, wired_state_one_sensor
            )
        )
        await wait_for_condition(
            lambda: adapter._scanning,
            description="adapter scanning started",
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
            adapter.inject_async(reading)
        await wait_for_condition(
            lambda: any(t == "office/state" for t, _, _ in ctx.published),
            description="sensor state published",
        )

        ctx._shutdown = True
        await asyncio.wait_for(task, timeout=3.0)

        # Assert — sensor state published under office (restored mapping)
        sensor_topics = [t for t, _p, _r in ctx.published if t == "office/state"]
        assert len(sensor_topics) >= 1
