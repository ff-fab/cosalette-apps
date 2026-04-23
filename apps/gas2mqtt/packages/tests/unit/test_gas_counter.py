"""Unit tests for gas2mqtt gas_counter telemetry handler.

Test Techniques Used:
- Specification-based: Verify payload structure, state changes, edge detection
- Equivalence Partitioning: Trigger command variants (valid, invalid, empty)
- Boundary Value Analysis: Counter wrap-around at COUNTER_MODULUS
- Error Guessing: OSError propagation, invalid JSON payloads
"""

from __future__ import annotations

import logging

import pytest
from cosalette import DeviceStore, MemoryStore, TriggerPayload

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.devices.gas_counter import (
    COUNTER_MODULUS,
    GasCounterState,
    gas_counter,
    make_gas_counter,
)
from tests.fixtures.config import make_gas2mqtt_settings

# Default Schmitt trigger thresholds (level=-5000, hysteresis=700):
# Upper threshold: -5000 + 700 = -4300  (triggers LOW -> HIGH)
# Lower threshold: -5000 - 700 = -5700  (triggers HIGH -> LOW)
BZ_HIGH = -4000  # Above upper threshold -> state HIGH
BZ_LOW = -6000  # Below lower threshold -> state LOW
BZ_NEUTRAL = -5000  # Inside hysteresis band -> no change

_logger = logging.getLogger("test")


def _make_test_state(
    *,
    enable_consumption: bool = False,
    liters_per_tick: float = 10.0,
    saved_counter: int = 0,
    saved_consumption: float | None = None,
) -> GasCounterState:
    """Create a GasCounterState for testing."""
    settings = make_gas2mqtt_settings(
        enable_consumption_tracking=enable_consumption,
        liters_per_tick=liters_per_tick,
    )
    store = DeviceStore(MemoryStore(), "gas_counter")
    store.load()
    if saved_counter != 0:
        store.update({"counter": saved_counter})
    if saved_consumption is not None:
        store.update({"consumption_m3": saved_consumption})
    store.save()
    return make_gas_counter(settings, store, _logger)


@pytest.mark.unit
class TestGasCounterInitialState:
    """Verify correct initial state from make_gas_counter factory."""

    def test_initial_state_fresh_store(self) -> None:
        """Fresh store creates counter=0, trigger=OPEN."""
        state = _make_test_state()

        result = state.build_state()

        assert result == {"counter": 0, "trigger": "OPEN"}

    def test_initial_state_with_consumption_enabled(self) -> None:
        """Initial state includes consumption_m3 when tracking enabled."""
        state = _make_test_state(enable_consumption=True)

        result = state.build_state()

        assert result == {"counter": 0, "trigger": "OPEN", "consumption_m3": 0.0}

    def test_initial_state_without_consumption(self) -> None:
        """State omits consumption_m3 when tracking disabled."""
        state = _make_test_state(enable_consumption=False)

        result = state.build_state()

        assert "consumption_m3" not in result

    def test_restores_counter_from_saved_state(self) -> None:
        """Counter restored from store on startup."""
        state = _make_test_state(saved_counter=42)

        result = state.build_state()

        assert result["counter"] == 42

    def test_restores_consumption_from_saved_state(self) -> None:
        """Consumption restored from store when tracking enabled."""
        state = _make_test_state(
            enable_consumption=True,
            saved_consumption=123.456,
        )

        result = state.build_state()

        assert result["consumption_m3"] == 123.456


@pytest.mark.unit
class TestGasCounterTriggerDetection:
    """Verify trigger event detection and state changes."""

    async def test_returns_none_when_no_trigger_event(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Handler returns None when Bz in hysteresis band (no MQTT chatter)."""
        fake_magnetometer.bz = BZ_NEUTRAL
        state = _make_test_state()

        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result is None

    async def test_publishes_on_rising_edge(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """State published when Bz crosses above upper threshold (LOW->HIGH)."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state()

        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result == {"counter": 1, "trigger": "CLOSED"}

    async def test_publishes_on_falling_edge(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """State published when Bz crosses below lower threshold (HIGH->LOW)."""
        # First trigger rising edge to get to HIGH state
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state()
        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)

        # Then trigger falling edge
        fake_magnetometer.bz = BZ_LOW
        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result == {"counter": 1, "trigger": "OPEN"}


@pytest.mark.unit
class TestGasCounterIncrement:
    """Verify counter increments and wrap-around."""

    async def test_counter_increments_on_rising_edge(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Counter increments by 1 on each LOW->HIGH transition."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state()

        # First rising edge
        result1 = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        # Return to LOW
        fake_magnetometer.bz = BZ_LOW
        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)

        # Second rising edge
        fake_magnetometer.bz = BZ_HIGH
        result2 = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result1["counter"] == 1
        assert result2["counter"] == 2

    async def test_counter_wraps_at_max(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Counter wraps to 0 after reaching COUNTER_MODULUS."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state(saved_counter=COUNTER_MODULUS - 1)

        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result["counter"] == 0

    async def test_falling_edge_does_not_increment(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Falling edge publishes state but does not increment counter."""
        # Start HIGH, then go LOW (falling edge)
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state()
        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)

        fake_magnetometer.bz = BZ_LOW
        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result["counter"] == 1  # Unchanged from rising edge


@pytest.mark.unit
class TestGasCounterConsumption:
    """Verify consumption tracking behavior."""

    async def test_consumption_increments_on_rising_edge(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Consumption increases by liters_per_tick converted to m³ on rising edge."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state(enable_consumption=True, liters_per_tick=10.0)

        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result["consumption_m3"] == 0.01  # 10 liters = 0.01 m3

    async def test_multiple_ticks_accumulate(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Multiple ticks accumulate consumption correctly."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state(enable_consumption=True, liters_per_tick=5.0)

        # First tick
        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)
        fake_magnetometer.bz = BZ_LOW
        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)

        # Second tick
        fake_magnetometer.bz = BZ_HIGH
        result = await gas_counter(
            state, TriggerPayload.scheduled(), fake_magnetometer, _logger
        )

        assert result["consumption_m3"] == 0.01  # 2 * 5L = 10L = 0.01 m3


@pytest.mark.unit
class TestGasCounterCommand:
    """Verify MQTT command handling."""

    async def test_command_sets_consumption(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """MQTT command sets consumption and publishes updated state."""
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt('{"consumption_m3": 123.456}')

        result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result["consumption_m3"] == 123.456

    async def test_command_ignored_when_consumption_disabled(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Command ignored when consumption tracking disabled."""
        state = _make_test_state(enable_consumption=False)
        trigger = TriggerPayload.from_mqtt('{"consumption_m3": 123.456}')

        result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result is None

    async def test_command_empty_payload_ignored(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Empty command payload is ignored."""
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt("")

        result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result is None

    async def test_command_invalid_json_ignored(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Invalid JSON in command payload is silently ignored (framework parses JSON)."""
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt("not json")

        result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result is None

    async def test_command_without_consumption_key_ignored(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """Command without consumption_m3 key is ignored."""
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt('{"other_key": 42}')

        result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result is None

    @pytest.mark.parametrize(
        ("payload", "warning_fragment"),
        [
            ('{"consumption_m3": "not-a-number"}', "invalid consumption_m3"),
            ('{"consumption_m3": null}', "invalid consumption_m3"),
            ('{"consumption_m3": "nan"}', "non-finite consumption_m3"),
            ('{"consumption_m3": "inf"}', "non-finite consumption_m3"),
            ('{"consumption_m3": -1}', "negative consumption_m3"),
            ('{"consumption_m3": 1000000.1}', "out-of-range consumption_m3"),
        ],
    )
    async def test_command_invalid_consumption_value_ignored(
        self,
        fake_magnetometer: FakeMagnetometer,
        caplog: pytest.LogCaptureFixture,
        payload: str,
        warning_fragment: str,
    ) -> None:
        """Invalid consumption values are rejected without mutating state.

        Technique: Equivalence Partitioning — non-numeric, non-finite,
        negative, and out-of-range payload classes.
        """
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt(payload)

        with caplog.at_level(logging.WARNING):
            result = await gas_counter(state, trigger, fake_magnetometer, _logger)

        assert result is None
        assert state.store.get("consumption_m3") is None
        assert warning_fragment in caplog.text


@pytest.mark.unit
class TestGasCounterErrorHandling:
    """Verify error handling behavior."""

    async def test_i2c_error_propagates(self) -> None:
        """OSError from magnetometer propagates (framework handles retry)."""
        error_mag = FakeMagnetometer()
        error_mag.initialize()
        error_mag.error_on_read = OSError("I2C bus error")
        state = _make_test_state()

        with pytest.raises(OSError, match="I2C bus error"):
            await gas_counter(state, TriggerPayload.scheduled(), error_mag, _logger)


@pytest.mark.unit
class TestGasCounterStatePersistence:
    """Verify state saving and restoration."""

    async def test_saves_state_after_tick(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """State is saved after counter increment."""
        fake_magnetometer.bz = BZ_HIGH
        state = _make_test_state()

        await gas_counter(state, TriggerPayload.scheduled(), fake_magnetometer, _logger)

        # Verify store was updated
        assert state.store.get("counter") == 1

    async def test_saves_state_after_command(
        self, fake_magnetometer: FakeMagnetometer
    ) -> None:
        """State is saved after consumption command."""
        state = _make_test_state(enable_consumption=True)
        trigger = TriggerPayload.from_mqtt('{"consumption_m3": 100.5}')

        await gas_counter(state, trigger, fake_magnetometer, _logger)

        # Verify store was updated
        assert state.store.get("consumption_m3") == 100.5

    def test_starts_fresh_with_empty_store(self) -> None:
        """Fresh store initializes with counter=0, no consumption."""
        state = _make_test_state()

        assert state.counter == 0
        assert state.consumption is None

    def test_full_roundtrip_restart(self) -> None:
        """Full save/restore cycle preserves all state."""
        from cosalette import MemoryStore as _MemoryStore

        shared_backend = _MemoryStore()
        settings = make_gas2mqtt_settings(enable_consumption_tracking=True)

        # First session - save some state
        store1 = DeviceStore(shared_backend, "gas_counter")
        state1 = make_gas_counter(settings, store1, _logger)
        state1.counter = 42
        state1.consumption.set_consumption(123.456)  # type: ignore[union-attr]
        state1.stage_state()
        store1.save()

        # Second session - new DeviceStore on same backend simulates restart
        store2 = DeviceStore(shared_backend, "gas_counter")
        state2 = make_gas_counter(settings, store2, _logger)

        # Verify restoration
        assert state2.counter == 42
        assert state2.consumption.consumption_m3 == 123.456  # type: ignore[union-attr]
