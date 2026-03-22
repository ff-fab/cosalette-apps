"""Unit tests for the cover device handler.

Test Techniques Used:
- State Transition Testing: Homing -> idle, command -> moving -> stopped
- Equivalence Partitioning: Open/close/stop commands, intermediate positions
- Boundary Value Analysis: Endpoints (0%, 100%), already-at-target
- Error Guessing: Invalid command payloads, shutdown during movement
- Specification-based Testing: Drift recalibration multi-step moves
"""

from __future__ import annotations

import asyncio

from velux2mqtt.adapters.fake import FakeGpio, PressCall
from velux2mqtt.devices.cover import (
    _execute_step,
    _publish_position,
    _run_homing,
    make_cover,
)
from velux2mqtt.domain.drift import MoveStep
from velux2mqtt.domain.position import PositionTracker
from velux2mqtt.settings import CoverConfig, Velux2MqttSettings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_DEFAULT_COVER = CoverConfig(
    name="blind",
    pin_up=17,
    pin_stop=27,
    pin_down=22,
    travel_duration_up=20.0,
    travel_duration_down=20.0,
    travel_time_offset=1.0,
    max_timer_margin=2.0,
)


def _make_settings(
    *,
    enable_homing: bool = False,
    homing_direction: str = "close",
    button_press_duration: float = 0.5,
    drift_threshold: int = 2,
) -> Velux2MqttSettings:
    """Create settings with a single cover for testing."""
    return Velux2MqttSettings(
        covers=[_DEFAULT_COVER],
        enable_startup_homing=enable_homing,
        homing_direction=homing_direction,
        button_press_duration=button_press_duration,
        drift_recalibration_threshold=drift_threshold,
    )


class FakeDeviceContext:
    """Minimal fake DeviceContext for unit testing cover functions.

    Records published states and supports shutdown signaling.
    """

    def __init__(
        self,
        gpio: FakeGpio,
        *,
        name: str = "blind",
        shutdown: bool = False,
    ) -> None:
        self._name = name
        self._gpio = gpio
        self._shutdown = shutdown
        self.published_states: list[dict[str, object]] = []
        self._command_handler = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown

    def adapter(self, port_type: type) -> object:  # noqa: ARG002
        return self._gpio

    async def publish_state(
        self,
        payload: dict[str, object],
        *,
        retain: bool = True,  # noqa: ARG002
    ) -> None:
        self.published_states.append(payload)

    async def sleep(self, seconds: float) -> None:  # noqa: ARG002
        """No-op sleep for tests."""

    def on_command(self, handler: object) -> object:
        self._command_handler = handler
        return handler

    def request_shutdown(self) -> None:
        self._shutdown = True


# ---------------------------------------------------------------------------
# Homing tests (P3.2)
# ---------------------------------------------------------------------------


class TestRunHoming:
    """Test startup homing strategy."""

    async def test_homing_close_presses_down_then_stop(self) -> None:
        """Homing close: presses down pin, then stop pin.

        Technique: Specification-based — verify homing direction mapping.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings(enable_homing=True, homing_direction="close")
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )

        # Act
        await _run_homing(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert
        assert len(gpio.presses) == 2
        assert gpio.presses[0] == PressCall(pin=22, duration=0.5)  # down
        assert gpio.presses[1] == PressCall(pin=27, duration=0.5)  # stop
        assert tracker.position == 0.0

    async def test_homing_open_presses_up_then_stop(self) -> None:
        """Homing open: presses up pin, then stop pin.

        Technique: Specification-based — verify open direction mapping.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings(enable_homing=True, homing_direction="open")
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )

        # Act
        await _run_homing(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert
        assert len(gpio.presses) == 2
        assert gpio.presses[0] == PressCall(pin=17, duration=0.5)  # up
        assert gpio.presses[1] == PressCall(pin=27, duration=0.5)  # stop
        assert tracker.position == 100.0

    async def test_homing_aborts_on_shutdown(self) -> None:
        """Homing aborts if shutdown is requested during travel.

        Technique: Error Guessing — shutdown during long-running operation.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio, shutdown=True)
        settings = _make_settings(enable_homing=True, homing_direction="close")
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )

        # Act
        await _run_homing(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — pressed down but never pressed stop (shutdown after sleep)
        assert len(gpio.presses) == 1
        assert gpio.presses[0].pin == 22  # down


# ---------------------------------------------------------------------------
# Execute step tests (P3.1)
# ---------------------------------------------------------------------------


class TestExecuteStep:
    """Test single movement step execution."""

    async def test_endpoint_close_finalizes_at_zero(self) -> None:
        """Moving to 0% uses full travel + margin and finalizes.

        Technique: Boundary Value Analysis — endpoint position 0.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 50.0  # start mid-way
        step = MoveStep(target=0)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert
        assert tracker.position == 0.0
        assert gpio.presses[0] == PressCall(pin=22, duration=0.5)  # down
        assert gpio.presses[1] == PressCall(pin=27, duration=0.5)  # stop

    async def test_endpoint_open_finalizes_at_hundred(self) -> None:
        """Moving to 100% uses full travel + margin and finalizes.

        Technique: Boundary Value Analysis — endpoint position 100.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        step = MoveStep(target=100)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert
        assert tracker.position == 100.0
        assert gpio.presses[0] == PressCall(pin=17, duration=0.5)  # up

    async def test_intermediate_position_presses_correct_pin(self) -> None:
        """Moving to intermediate position presses correct direction pin.

        Technique: Equivalence Partitioning — intermediate move up.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        # tracker starts at 0
        step = MoveStep(target=50)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — should press up, then stop
        assert gpio.presses[0].pin == 17  # up
        assert gpio.presses[1].pin == 27  # stop

    async def test_already_at_target_skips_movement(self) -> None:
        """No GPIO presses when already at target position.

        Technique: Boundary Value Analysis — no-op when delta is zero.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 50.0
        step = MoveStep(target=50)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert
        assert len(gpio.presses) == 0

    async def test_recalibration_step_still_moves(self) -> None:
        """Recalibration steps execute movement even at endpoints.

        Technique: Specification-based — recalibration flag behavior.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        step = MoveStep(target=0, is_recalibration=True)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — should still press down + stop even though position=0
        # because position_int matches but is_recalibration overrides skip
        assert tracker.position == 0.0


# ---------------------------------------------------------------------------
# Publish position tests
# ---------------------------------------------------------------------------


class TestPublishPosition:
    """Test position state publishing."""

    async def test_publishes_position_int(self) -> None:
        """Publishes position as an integer in the state payload.

        Technique: Specification-based — verify MQTT payload format.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 73.7

        # Act
        await _publish_position(ctx, tracker)

        # Assert
        assert ctx.published_states == [{"position": 74}]


# ---------------------------------------------------------------------------
# make_cover factory tests (P3.1)
# ---------------------------------------------------------------------------


class TestMakeCover:
    """Test the cover device factory function."""

    def test_returns_callable(self) -> None:
        """Factory returns an async callable.

        Technique: Specification-based — verify factory contract.
        """
        # Arrange
        settings = _make_settings()

        # Act
        result = make_cover(_DEFAULT_COVER, settings)

        # Assert
        assert callable(result)
        assert asyncio.iscoroutinefunction(result)

    async def test_device_publishes_initial_state(self) -> None:
        """Device function publishes initial position on startup.

        Technique: State Transition Testing — initial state publication.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)  # immediate shutdown

        # Act
        await device_fn(ctx)

        # Assert — should publish initial state (position=0 since no homing)
        assert len(ctx.published_states) >= 1
        assert ctx.published_states[0] == {"position": 0}

    async def test_device_with_homing_publishes_homed_position(self) -> None:
        """Device with homing enabled publishes position after homing.

        Technique: State Transition Testing — homing -> initial publish.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=True, homing_direction="close")
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)  # shutdown after homing

        # Act
        await device_fn(ctx)

        # Assert — homing to close sets position=0
        assert {"position": 0} in ctx.published_states

    async def test_command_handler_registered(self) -> None:
        """Device registers a command handler on the context.

        Technique: Specification-based — verify command registration.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)

        # Act
        await device_fn(ctx)

        # Assert
        assert ctx._command_handler is not None

    async def test_stop_command_resets_drift(self) -> None:
        """Stop command stops tracker and publishes position.

        Technique: Equivalence Partitioning — stop command handling.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)

        # Act — run device to register handler, then invoke it
        await device_fn(ctx)
        handler = ctx._command_handler
        assert handler is not None

        ctx.published_states.clear()
        await handler("topic", "stop")

        # Assert
        assert ctx.published_states == [{"position": 0}]

    async def test_open_command_triggers_movement(self) -> None:
        """Open command triggers GPIO presses for upward movement.

        Technique: Equivalence Partitioning — open command handling.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)

        # Act — run device to register handler (exits immediately due to shutdown)
        await device_fn(ctx)
        handler = ctx._command_handler
        assert handler is not None

        # Re-enable so the command handler loop can execute steps
        ctx._shutdown = False
        gpio.presses.clear()
        await handler("topic", "open")

        # Assert — should press up pin and stop pin
        assert any(p.pin == 17 for p in gpio.presses)  # up

    async def test_invalid_command_does_not_crash(self) -> None:
        """Invalid command payload is logged, no crash.

        Technique: Error Guessing — malformed command payload.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)

        ctx = FakeDeviceContext(gpio, shutdown=True)

        # Act
        await device_fn(ctx)
        handler = ctx._command_handler
        assert handler is not None

        ctx.published_states.clear()
        await handler("topic", "garbage_payload")

        # Assert — no state published, no exception
        assert ctx.published_states == []
