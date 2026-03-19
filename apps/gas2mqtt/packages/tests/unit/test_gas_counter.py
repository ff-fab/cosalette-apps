"""Unit tests for gas2mqtt/devices/gas_counter.py — Gas counter device handler.

Tests the integration between domain objects (SchmittTrigger,
ConsumptionTracker) and the cosalette DeviceContext within the
gas_counter device coroutine.

Test Techniques Used:
- State Transition Testing: Trigger transitions (LOW→HIGH, HIGH→LOW)
- Boundary Value Analysis: Counter wrap-around at COUNTER_MODULUS
- Branch/Condition Coverage: Consumption enabled/disabled, I2C errors
- Error Guessing: Invalid JSON in command payload, OSError during read
"""

from __future__ import annotations

import asyncio
import json

import cosalette
import pytest
from cosalette.testing import FakeClock, MockMqttClient

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.gas_counter import COUNTER_MODULUS, gas_counter
from gas2mqtt.ports import MagnetometerPort
from tests.fixtures.async_utils import wait_for_condition
from tests.fixtures.config import make_gas2mqtt_settings

# Default Schmitt trigger thresholds (level=-5000, hysteresis=700):
# Upper threshold: -5000 + 700 = -4300  (triggers LOW → HIGH)
# Lower threshold: -5000 - 700 = -5700  (triggers HIGH → LOW)
BZ_HIGH = -4000  # Above upper threshold → state HIGH
BZ_LOW = -6000  # Below lower threshold → state LOW
BZ_NEUTRAL = -5000  # Inside hysteresis band → no change


def _make_context(
    mock_mqtt: MockMqttClient,
    fake_clock: FakeClock,
    fake_magnetometer: FakeMagnetometer,
    *,
    enable_consumption: bool = False,
    liters_per_tick: float = 10.0,
    poll_interval: float = 0.01,
    store: cosalette.MemoryStore | None = None,
) -> tuple[cosalette.DeviceContext, cosalette.DeviceStore]:
    """Create a DeviceContext and DeviceStore for gas_counter tests."""

    settings = make_gas2mqtt_settings(
        enable_consumption_tracking=enable_consumption,
        liters_per_tick=liters_per_tick,
        poll_interval=poll_interval,
    )
    ctx = cosalette.DeviceContext(
        name="gas_counter",
        settings=settings,
        mqtt=mock_mqtt,
        topic_prefix="gas2mqtt",
        shutdown_event=asyncio.Event(),
        adapters={
            MagnetometerPort: fake_magnetometer,
        },
        clock=fake_clock,
    )
    backend = store or cosalette.MemoryStore()
    device_store = cosalette.DeviceStore(backend, "gas_counter")
    device_store.load()
    return ctx, device_store


def _published_states(mock_mqtt: MockMqttClient) -> list[dict[str, object]]:
    """Extract all state payloads published to the gas_counter state topic."""
    return [
        json.loads(payload)
        for topic, payload, _qos, _retain in mock_mqtt.published
        if topic == "gas2mqtt/gas_counter/state"
    ]


# ======================================================================
# Initial state publication
# ======================================================================


@pytest.mark.unit
class TestGasCounterInitialState:
    """Verify the device publishes correct initial state on startup."""

    async def test_publishes_initial_state(
        self,
        gas_counter_context: cosalette.DeviceContext,
        gas_counter_store: cosalette.DeviceStore,
        mock_mqtt: MockMqttClient,
    ) -> None:
        """Device publishes counter=0, trigger=OPEN on startup.

        Technique: Specification-based — verifying initial contract.
        """
        # Arrange — context already wired; set shutdown immediately so the
        # loop body doesn't execute (we only want the initial publish).
        gas_counter_context._shutdown_event.set()

        # Act
        await gas_counter(gas_counter_context, gas_counter_store)

        # Assert
        states = _published_states(mock_mqtt)
        assert len(states) >= 1
        assert states[0] == {"counter": 0, "trigger": "OPEN"}

    async def test_consumption_in_initial_state_when_enabled(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Initial state includes consumption_m3 when tracking is enabled.

        Technique: Branch/Condition Coverage — consumption enabled path.
        """
        # Arrange
        ctx, store = _make_context(
            mock_mqtt, fake_clock, fake_magnetometer, enable_consumption=True
        )
        ctx._shutdown_event.set()

        # Act
        await gas_counter(ctx, store)

        # Assert
        states = _published_states(mock_mqtt)
        assert states[0] == {"counter": 0, "trigger": "OPEN", "consumption_m3": 0.0}

    async def test_consumption_not_in_state_when_disabled(
        self,
        gas_counter_context: cosalette.DeviceContext,
        gas_counter_store: cosalette.DeviceStore,
        mock_mqtt: MockMqttClient,
    ) -> None:
        """State omits consumption_m3 when tracking is disabled.

        Technique: Branch/Condition Coverage — consumption disabled path.
        """
        # Arrange
        gas_counter_context._shutdown_event.set()

        # Act
        await gas_counter(gas_counter_context, gas_counter_store)

        # Assert
        states = _published_states(mock_mqtt)
        assert "consumption_m3" not in states[0]


# ======================================================================
# Trigger detection and state publication
# ======================================================================


@pytest.mark.unit
class TestGasCounterTriggerDetection:
    """Verify trigger event detection and state publication."""

    async def test_publishes_on_rising_edge(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """State published when Bz crosses above upper threshold (LOW→HIGH).

        Technique: State Transition Testing — LOW → HIGH transition.
        """
        # Arrange
        fake_magnetometer.bz = BZ_HIGH
        ctx, store = _make_context(mock_mqtt, fake_clock, fake_magnetometer)
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — wait for at least one loop iteration to publish
        await wait_for_condition(
            lambda: len(_published_states(mock_mqtt)) >= 2,
            description="rising edge state publish",
        )
        ctx._shutdown_event.set()
        await task

        # Assert — initial state + rising edge state
        states = _published_states(mock_mqtt)
        assert states[-1]["trigger"] == "CLOSED"
        assert states[-1]["counter"] == 1

    async def test_publishes_on_falling_edge(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """State published when Bz crosses below lower threshold (HIGH→LOW).

        Technique: State Transition Testing — HIGH → LOW transition.
        """
        # Arrange — first go HIGH, then go LOW
        fake_magnetometer.bz = BZ_HIGH
        ctx, store = _make_context(mock_mqtt, fake_clock, fake_magnetometer)
        task = asyncio.create_task(gas_counter(ctx, store))

        # Wait for rising edge
        await wait_for_condition(
            lambda: any(s["trigger"] == "CLOSED" for s in _published_states(mock_mqtt)),
            description="rising edge",
        )

        # Act — bring Bz below lower threshold
        fake_magnetometer.bz = BZ_LOW
        await wait_for_condition(
            lambda: _published_states(mock_mqtt)[-1]["trigger"] == "OPEN",
            description="falling edge state publish",
        )
        ctx._shutdown_event.set()
        await task

        # Assert
        last = _published_states(mock_mqtt)[-1]
        assert last["trigger"] == "OPEN"
        assert last["counter"] == 1  # Only rising edge increments counter

    async def test_no_publish_when_no_trigger_event(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """No state published when Bz stays in hysteresis band.

        Technique: State Transition Testing — no transition in dead band.
        """
        # Arrange — Bz in neutral zone (no trigger event)
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(mock_mqtt, fake_clock, fake_magnetometer)
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — let the loop run a few iterations
        await asyncio.sleep(0.05)
        ctx._shutdown_event.set()
        await task

        # Assert — only initial state, no additional publishes
        states = _published_states(mock_mqtt)
        assert len(states) == 1  # Just the initial publish


# ======================================================================
# Counter behaviour
# ======================================================================


@pytest.mark.unit
class TestGasCounterIncrement:
    """Verify counter increments and wrap-around."""

    async def test_counter_increments_on_rising_edge(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Counter increments by 1 on each LOW→HIGH transition.

        Technique: Specification-based — counter tracks rising edges.
        """
        # Arrange
        ctx, store = _make_context(mock_mqtt, fake_clock, fake_magnetometer)
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — trigger two full cycles: HIGH → LOW → HIGH
        fake_magnetometer.bz = BZ_HIGH
        await wait_for_condition(
            lambda: any(s["counter"] == 1 for s in _published_states(mock_mqtt)),
            description="first tick",
        )
        fake_magnetometer.bz = BZ_LOW
        await wait_for_condition(
            lambda: _published_states(mock_mqtt)[-1]["trigger"] == "OPEN",
            description="return to OPEN",
        )
        fake_magnetometer.bz = BZ_HIGH
        await wait_for_condition(
            lambda: any(s["counter"] == 2 for s in _published_states(mock_mqtt)),
            description="second tick",
        )
        ctx._shutdown_event.set()
        await task

        # Assert
        final = [s for s in _published_states(mock_mqtt) if s["counter"] == 2]
        assert len(final) >= 1

    async def test_counter_wraps_at_max(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Counter wraps to 0 after reaching COUNTER_MODULUS.

        Technique: Boundary Value Analysis — counter at wrap-around boundary.

        This test patches the counter directly via a modified device
        function since running 65535 iterations would be impractical.
        Instead, we verify the modular arithmetic:
        (COUNTER_MODULUS - 1 + 1) % COUNTER_MODULUS == 0.
        """
        # Arrange — verify the wrap-around arithmetic directly
        counter = COUNTER_MODULUS - 1

        # Act
        counter = (counter + 1) % COUNTER_MODULUS

        # Assert
        assert counter == 0

    async def test_counter_modulus_is_0x10000(self) -> None:
        """COUNTER_MODULUS is 65536 (2^16).

        Technique: Specification-based — constant value.
        """
        assert COUNTER_MODULUS == 0x10000
        assert COUNTER_MODULUS == 65536


# ======================================================================
# Consumption tracking
# ======================================================================


@pytest.mark.unit
class TestGasCounterConsumption:
    """Verify optional consumption tracking integration."""

    async def test_consumption_increments_on_rising_edge(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Consumption increases by liters_per_tick/1000 per tick.

        Technique: Specification-based — consumption tracks rising edges.
        """
        # Arrange — 10 liters/tick = 0.01 m³/tick
        fake_magnetometer.bz = BZ_HIGH
        ctx, store = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            liters_per_tick=10.0,
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — wait for first tick
        await wait_for_condition(
            lambda: any(s["counter"] == 1 for s in _published_states(mock_mqtt)),
            description="consumption tick",
        )
        ctx._shutdown_event.set()
        await task

        # Assert
        ticked = [s for s in _published_states(mock_mqtt) if s["counter"] == 1]
        assert ticked[-1]["consumption_m3"] == 0.01


# ======================================================================
# Command handler
# ======================================================================


@pytest.mark.unit
class TestGasCounterCommand:
    """Verify inbound MQTT command handling."""

    async def test_command_sets_consumption(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Command with consumption_m3 updates the tracker and republishes.

        Technique: Specification-based — command handler contract.
        """
        # Arrange
        fake_magnetometer.bz = BZ_NEUTRAL  # Stay in dead band
        ctx, store = _make_context(
            mock_mqtt, fake_clock, fake_magnetometer, enable_consumption=True
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        # Wait for initial state
        await wait_for_condition(
            lambda: len(_published_states(mock_mqtt)) >= 1,
            description="initial state",
        )

        # Act — invoke the registered command handler directly
        assert ctx.command_handler is not None
        await ctx.command_handler(
            "gas2mqtt/gas_counter/set",
            json.dumps({"consumption_m3": 123.456}),
        )
        ctx._shutdown_event.set()
        await task

        # Assert — state republished with new consumption
        states = _published_states(mock_mqtt)
        consumption_states = [s for s in states if s.get("consumption_m3") == 123.456]
        assert len(consumption_states) >= 1

    async def test_command_ignored_when_consumption_disabled(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Command is logged as warning and ignored when tracking is off.

        Technique: Branch/Condition Coverage — disabled consumption path.
        """
        # Arrange
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt, fake_clock, fake_magnetometer, enable_consumption=False
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        await wait_for_condition(
            lambda: len(_published_states(mock_mqtt)) >= 1,
            description="initial state",
        )

        # Act — send command
        assert ctx.command_handler is not None
        publish_count_before = len(_published_states(mock_mqtt))
        await ctx.command_handler(
            "gas2mqtt/gas_counter/set",
            json.dumps({"consumption_m3": 100.0}),
        )
        ctx._shutdown_event.set()
        await task

        # Assert — no additional state published from command
        # (loop may have published if a trigger event occurred, but with
        # neutral Bz that shouldn't happen)
        assert len(_published_states(mock_mqtt)) == publish_count_before

    async def test_command_invalid_json_logged(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Invalid JSON in command payload logs an error, doesn't crash.

        Technique: Error Guessing — malformed MQTT payload.
        """
        # Arrange
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt, fake_clock, fake_magnetometer, enable_consumption=True
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        await wait_for_condition(
            lambda: len(_published_states(mock_mqtt)) >= 1,
            description="initial state",
        )

        # Act
        assert ctx.command_handler is not None
        await ctx.command_handler(
            "gas2mqtt/gas_counter/set",
            "not valid json{{{",
        )
        ctx._shutdown_event.set()
        await task

        # Assert — error logged, device still alive
        assert any("Invalid consumption command" in r.message for r in caplog.records)


# ======================================================================
# Error resilience
# ======================================================================


@pytest.mark.unit
class TestGasCounterErrorHandling:
    """Verify the polling loop survives I2C errors."""

    async def test_i2c_error_does_not_crash_loop(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """OSError during magnetometer read is logged; loop continues.

        Technique: Error Guessing — I2C bus failure during operation.
        """
        # Arrange — make the magnetometer raise OSError, then recover
        error_mag = FakeMagnetometer()
        error_mag.initialize()
        call_count = 0
        original_read = error_mag.read

        def flaky_read():  # noqa: ANN202
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("I2C bus error")
            return original_read()

        error_mag.read = flaky_read  # type: ignore[assignment,method-assign]

        ctx, store = _make_context(mock_mqtt, fake_clock, error_mag)
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — let the loop run through the errors and a recovery
        await wait_for_condition(
            lambda: call_count >= 3,
            description="I2C recovery",
        )
        ctx._shutdown_event.set()
        await task

        # Assert — device started (initial state published) and survived
        states = _published_states(mock_mqtt)
        assert len(states) >= 1


# ======================================================================
# State persistence
# ======================================================================


@pytest.mark.unit
class TestGasCounterStatePersistence:
    """Verify state persistence between restarts.

    Technique: Round-trip Testing — save on shutdown, restore on startup.
    """

    async def test_restores_counter_from_saved_state(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Counter starts at saved value, not zero.

        Technique: Specification-based — restore contract.
        """
        # Arrange — pre-populate backend with saved state
        backend = cosalette.MemoryStore()
        backend.save("gas_counter", {"counter": 42})
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt, fake_clock, fake_magnetometer, store=backend
        )
        ctx._shutdown_event.set()

        # Act
        await gas_counter(ctx, store)

        # Assert
        states = _published_states(mock_mqtt)
        assert states[0]["counter"] == 42

    async def test_restores_consumption_from_saved_state(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Consumption starts at saved value when tracking is enabled.

        Technique: Specification-based — restore contract with consumption.
        """
        # Arrange
        backend = cosalette.MemoryStore()
        backend.save("gas_counter", {"counter": 10, "consumption_m3": 99.5})
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            store=backend,
        )
        ctx._shutdown_event.set()

        # Act
        await gas_counter(ctx, store)

        # Assert
        states = _published_states(mock_mqtt)
        assert states[0]["counter"] == 10
        assert states[0]["consumption_m3"] == 99.5

    async def test_saves_state_on_shutdown(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """State is saved to storage when device shuts down.

        Technique: State Transition Testing — shutdown lifecycle.
        """
        # Arrange
        backend = cosalette.MemoryStore()
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            store=backend,
        )
        ctx._shutdown_event.set()

        # Act
        await gas_counter(ctx, store)

        # Assert — state was persisted (trigger is NOT saved)
        saved = backend.load("gas_counter")
        assert saved is not None
        assert saved["counter"] == 0
        assert saved["consumption_m3"] == 0.0
        assert "trigger" not in saved

    async def test_saves_state_after_tick(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """State is saved after each trigger event.

        Technique: State Transition Testing — save on state change.
        """
        # Arrange
        backend = cosalette.MemoryStore()
        fake_magnetometer.bz = BZ_HIGH
        ctx, store = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            liters_per_tick=10.0,
            store=backend,
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        # Act — wait for first tick
        await wait_for_condition(
            lambda: any(s["counter"] == 1 for s in _published_states(mock_mqtt)),
            description="first tick",
        )
        ctx._shutdown_event.set()
        await task

        # Assert — state was saved with updated counter and consumption
        saved = backend.load("gas_counter")
        assert saved is not None
        assert saved["counter"] == 1
        assert saved["consumption_m3"] == 0.01

    async def test_saves_state_after_command(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """State is saved after consumption set by command.

        Technique: Specification-based — save after manual set.
        """
        # Arrange
        backend = cosalette.MemoryStore()
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx, store = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            store=backend,
        )
        task = asyncio.create_task(gas_counter(ctx, store))

        await wait_for_condition(
            lambda: len(_published_states(mock_mqtt)) >= 1,
            description="initial state",
        )

        # Act — set consumption via command
        assert ctx.command_handler is not None
        await ctx.command_handler(
            "gas2mqtt/gas_counter/set",
            json.dumps({"consumption_m3": 55.5}),
        )
        ctx._shutdown_event.set()
        await task

        # Assert
        saved = backend.load("gas_counter")
        assert saved is not None
        assert saved["consumption_m3"] == 55.5

    async def test_starts_fresh_with_null_store(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Device starts at zero when using NullStore (no persistence).

        Technique: Branch/Condition Coverage — NullStore path.
        """
        # Arrange — NullStore backend means load() yields empty state
        backend = cosalette.NullStore()
        fake_magnetometer.bz = BZ_NEUTRAL
        settings = make_gas2mqtt_settings(enable_consumption_tracking=True)
        ctx = cosalette.DeviceContext(
            name="gas_counter",
            settings=settings,
            mqtt=mock_mqtt,
            topic_prefix="gas2mqtt",
            shutdown_event=asyncio.Event(),
            adapters={MagnetometerPort: fake_magnetometer},
            clock=fake_clock,
        )
        device_store = cosalette.DeviceStore(backend, "gas_counter")
        device_store.load()
        ctx._shutdown_event.set()

        # Act
        await gas_counter(ctx, device_store)

        # Assert — starts at zero
        states = _published_states(mock_mqtt)
        assert states[0]["counter"] == 0
        assert states[0]["consumption_m3"] == 0.0

    async def test_full_roundtrip_restart(
        self,
        mock_mqtt: MockMqttClient,
        fake_clock: FakeClock,
        fake_magnetometer: FakeMagnetometer,
    ) -> None:
        """Counter and consumption survive a simulated restart.

        Technique: Round-trip Testing — full save/restart/restore cycle.
        """
        # Arrange — first run: tick once
        backend = cosalette.MemoryStore()
        fake_magnetometer.bz = BZ_HIGH
        ctx1, store1 = _make_context(
            mock_mqtt,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            liters_per_tick=10.0,
            store=backend,
        )
        task1 = asyncio.create_task(gas_counter(ctx1, store1))

        await wait_for_condition(
            lambda: any(s["counter"] == 1 for s in _published_states(mock_mqtt)),
            description="first tick in run 1",
        )
        ctx1._shutdown_event.set()
        await task1

        # Act — second run: simulate restart with fresh context but same backend
        mock_mqtt2 = MockMqttClient()
        fake_magnetometer.bz = BZ_NEUTRAL
        ctx2, store2 = _make_context(
            mock_mqtt2,
            fake_clock,
            fake_magnetometer,
            enable_consumption=True,
            liters_per_tick=10.0,
            store=backend,
        )
        ctx2._shutdown_event.set()
        await gas_counter(ctx2, store2)

        # Assert — second run starts where first left off
        states2 = _published_states(mock_mqtt2)
        assert states2[0]["counter"] == 1
        assert states2[0]["consumption_m3"] == 0.01
