"""Unit tests for the cover device handler.

Test Techniques Used:
- State Transition Testing: Homing -> idle, command -> moving -> stopped,
  calibration IDLE -> READY -> TIMING -> COMPLETE
- Equivalence Partitioning: Open/close/stop commands, intermediate positions,
  calibration actions (start/go/mark/cancel)
- Boundary Value Analysis: Endpoints (0%, 100%), already-at-target
- Error Guessing: Invalid command payloads, shutdown during movement,
  normal commands blocked during calibration, invalid calibration transitions
- Specification-based Testing: Drift recalibration multi-step moves,
  calibration MQTT status publishing, result publishing on completion,
  dead band traversal on open/close
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest

from velux2mqtt.adapters.fake import FakeGpio, PressCall
from velux2mqtt.devices.cover import (
    _dead_band_time,
    _execute_step,
    _parse_calibrate,
    _publish_position,
    _run_active_calibration_session,
    _run_homing,
    make_cover,
)
from velux2mqtt.domain.calibration import CalibrationStateMachine
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
    measure_offset=True,
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


@dataclass(frozen=True)
class FakeCommand:
    """Minimal fake Command for ctx.commands()."""

    payload: str
    topic: str = "test/topic"
    sub_topic: str = ""
    timestamp: float = 0.0


class FakeDeviceContext:
    """Minimal fake DeviceContext for unit testing cover functions.

    Records published states and supports shutdown signaling.
    With ctx.commands() support via asyncio.Queue.
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
        self.published_channels: list[tuple[str, str]] = []
        self._command_queue: asyncio.Queue[FakeCommand] = asyncio.Queue()
        self._root_handler = None
        self._sub_handlers: dict[str, object] = {}
        self._active_sub_entities: dict[str, object] = {}

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

    async def publish(
        self,
        channel: str,
        payload: str,
        *,
        retain: bool = False,  # noqa: ARG002
        qos: int = 1,  # noqa: ARG002
    ) -> None:
        self.published_channels.append((channel, payload))

    async def sleep(self, seconds: float) -> None:  # noqa: ARG002
        """No-op sleep for tests."""

    async def commands(self) -> AsyncIterator[FakeCommand]:
        """Yield commands from the queue until shutdown requested."""
        while not self.shutdown_requested:
            try:
                cmd = await asyncio.wait_for(self._command_queue.get(), timeout=0.01)
                yield cmd
            except asyncio.TimeoutError:
                # Allow the loop to check shutdown_requested
                pass

    async def send_command(self, payload: str) -> None:
        """Send a command to the device for testing."""
        await self._command_queue.put(FakeCommand(payload=payload))

    def request_shutdown(self) -> None:
        self._shutdown = True

    def on_command(self, handler_or_sub_topic):
        """Register a command handler, optionally for a sub-topic."""
        if callable(handler_or_sub_topic):
            # Direct handler registration (root topic)
            self._root_handler = handler_or_sub_topic
            return handler_or_sub_topic
        else:
            # Sub-topic factory
            sub_topic = handler_or_sub_topic

            def decorator(handler):
                self._sub_handlers[sub_topic] = handler
                return handler

            return decorator

    def sub_entity(self, name: str):
        """Async context manager for sub-entity management."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _sub_entity_context():
            sub = FakeSubEntityContext(name=name, parent=self)
            self._active_sub_entities[name] = sub
            try:
                yield sub
            finally:
                del self._active_sub_entities[name]

        return _sub_entity_context()

    async def send_calibration_command(self, payload: str) -> None:
        """Invoke the registered calibrate sub-topic handler."""
        handler = self._sub_handlers.get("calibrate")
        if handler is not None:
            await handler(None, payload)


@dataclass
class FakeSubEntityContext:
    """Minimal fake SubEntityContext for unit testing calibration functions."""

    name: str
    parent: FakeDeviceContext
    published_states: list[dict[str, object]] = field(default_factory=list)

    async def publish_state(
        self, payload: dict[str, object], *, retain: bool = True
    ) -> None:
        self.published_states.append(payload)
        # Also record in parent's published_channels for backward compat
        import json

        self.parent.published_channels.append(
            (f"{self.name}/state", json.dumps(payload))
        )

    def on_command(self, handler):
        self.parent._sub_handlers[self.name] = handler
        return handler


class RepeatingCalibrationQueue:
    """Queue-like test double that yields the same calibration action forever."""

    def __init__(self, action: str) -> None:
        self._payload = {"action": action}

    async def get(self) -> dict[str, object]:
        return self._payload


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

        # Assert — pressed down, then best-effort stop on shutdown
        assert len(gpio.presses) == 2
        assert gpio.presses[0].pin == 22  # down
        assert gpio.presses[1].pin == 27  # stop (best-effort)


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

        # Assert — endpoint moves skip the STOP press (motor stalls at limit)
        assert tracker.position == 0.0
        assert len(gpio.presses) == 1
        assert gpio.presses[0] == PressCall(pin=22, duration=0.5)  # down only

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

        # Assert — endpoint moves skip the STOP press (motor stalls at limit)
        assert tracker.position == 100.0
        assert len(gpio.presses) == 1
        assert gpio.presses[0] == PressCall(pin=17, duration=0.5)  # up only

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

    async def test_intermediate_downward_presses_down_pin(self) -> None:
        """Moving to lower intermediate position presses down pin.

        Technique: Equivalence Partitioning — intermediate move down.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 80.0
        step = MoveStep(target=30)

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

        # Assert — should press down, then stop
        assert gpio.presses[0].pin == 22  # down
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

        # Assert — should still press down even though position=0
        # because position_int matches but is_recalibration overrides skip
        assert tracker.position == 0.0
        assert len(gpio.presses) >= 1

    async def test_intermediate_position_still_sends_stop(self) -> None:
        """Intermediate moves (e.g. 50%) still get a STOP press.

        Technique: Equivalence Partitioning — non-endpoint target.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 20.0
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

        # Assert — intermediate move: direction press + stop press
        assert len(gpio.presses) == 2
        assert gpio.presses[0] == PressCall(pin=17, duration=0.5)  # up
        assert gpio.presses[1] == PressCall(pin=27, duration=0.5)  # stop

    async def test_endpoint_close_waits_full_travel_without_stop(self) -> None:
        """Endpoint close still waits full travel + margin, just no STOP.

        Technique: Specification-based — verify travel time preserved.
        """
        # Arrange
        sleep_times: list[float] = []

        class TimingCtx(FakeDeviceContext):
            async def sleep(self, seconds: float) -> None:
                sleep_times.append(seconds)

        gpio = FakeGpio()
        ctx = TimingCtx(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 50.0
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

        # Assert — full travel + configured margin waited, no STOP press
        expected_sleep = tracker.travel_duration_down + _DEFAULT_COVER.max_timer_margin
        assert sleep_times == [expected_sleep]
        assert len(gpio.presses) == 1  # only direction press, no stop
        assert gpio.presses[0].pin == _DEFAULT_COVER.pin_down


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

    async def test_device_processes_commands_via_ctx_commands(self) -> None:
        """Device processes commands via ctx.commands() instead of handler.

        Technique: Specification-based — verify new command processing pattern.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Act — run device as a task and send a command
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)  # Let device start
        await ctx.send_command("stop")
        await asyncio.sleep(0.01)  # Let device process command
        ctx.request_shutdown()
        await device_task

        # Assert — command was processed
        assert any(p.pin == 27 for p in gpio.presses)  # stop pin
        assert ctx.published_states == [
            {"position": 0},
            {"position": 0},
        ]  # initial + after stop

    async def test_stop_command_resets_drift(self) -> None:
        """Stop command stops tracker and publishes position.

        Technique: Equivalence Partitioning — stop command handling.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Act — run device and send stop command
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)
        ctx.published_states.clear()  # Clear initial state
        gpio.presses.clear()
        await ctx.send_command("stop")
        await asyncio.sleep(0.01)
        ctx.request_shutdown()
        await device_task

        # Assert — presses physical stop pin and publishes state
        assert any(p.pin == 27 for p in gpio.presses)  # stop pin
        assert {"position": 0} in ctx.published_states

    async def test_open_command_triggers_movement(self) -> None:
        """Open command triggers GPIO presses for upward movement.

        Technique: Equivalence Partitioning — open command handling.
        """
        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Act — run device and send open command
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)
        gpio.presses.clear()
        await ctx.send_command("open")
        await asyncio.sleep(0.01)
        ctx.request_shutdown()
        await device_task

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
        ctx = FakeDeviceContext(gpio)

        # Act — run device and send invalid command
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)
        ctx.published_states.clear()  # Clear initial state
        await ctx.send_command("garbage_payload")
        await asyncio.sleep(0.01)
        ctx.request_shutdown()
        await device_task

        # Assert — no additional state published, no exception
        assert ctx.published_states == []


# ---------------------------------------------------------------------------
# Calibration parsing tests
# ---------------------------------------------------------------------------


class TestParseCalibrate:
    """Test calibration payload parsing."""

    def test_valid_start_action(self) -> None:
        """Extracts 'start' from valid calibration JSON.

        Technique: Specification-based — verify parsing contract.
        """
        result = _parse_calibrate('{"phase": "start"}')
        assert result is not None
        assert result["action"] == "start"

    def test_start_with_runs(self) -> None:
        """Extracts runs parameter from start action."""
        result = _parse_calibrate('{"phase": "start", "runs": 5}')
        assert result is not None
        assert result["action"] == "start"
        assert result["runs"] == 5

    def test_valid_go_action(self) -> None:
        """Extracts 'go' from valid calibration JSON."""
        result = _parse_calibrate('{"phase": "go"}')
        assert result is not None
        assert result["action"] == "go"

    def test_valid_mark_action(self) -> None:
        """Extracts 'mark' from valid calibration JSON."""
        result = _parse_calibrate('{"phase": "mark"}')
        assert result is not None
        assert result["action"] == "mark"

    def test_valid_cancel_action(self) -> None:
        """Extracts 'cancel' from valid calibration JSON."""
        result = _parse_calibrate('{"phase": "cancel"}')
        assert result is not None
        assert result["action"] == "cancel"

    def test_non_json_returns_none(self) -> None:
        """Non-JSON payloads return None.

        Technique: Equivalence Partitioning — non-calibration payload.
        """
        assert _parse_calibrate("open") is None

    def test_unknown_action_returns_none(self) -> None:
        """Unknown calibrate action returns None."""
        assert _parse_calibrate('{"phase": "unknown"}') is None

    def test_position_json_returns_none(self) -> None:
        """Normal position JSON returns None (no phase key)."""
        assert _parse_calibrate('{"position": 50}') is None

    def test_invalid_json_returns_none(self) -> None:
        """Malformed JSON returns None."""
        assert _parse_calibrate("{bad json") is None


# ---------------------------------------------------------------------------
# Calibration integration tests (via make_cover device)
# ---------------------------------------------------------------------------


class TestCalibrationDispatch:
    """Test calibration commands dispatched through cover device."""

    async def _run_device_with_commands(
        self, commands: list[str], *, homing: bool = False
    ) -> tuple[FakeDeviceContext, FakeGpio]:
        """Run the cover device with a sequence of commands."""
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=homing)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Start device as task
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)  # Let device start

        # Send commands
        for cmd in commands:
            await ctx.send_command(cmd)
            await asyncio.sleep(0.01)  # Let device process

        # Shutdown
        ctx.request_shutdown()
        await device_task

        return ctx, gpio

    async def _run_device_with_calibration_commands(
        self, cal_commands: list[str], *, homing: bool = False
    ) -> tuple[FakeDeviceContext, FakeGpio]:
        """Run the cover device with a sequence of calibration commands."""
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=homing)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Start device as task
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)  # Let device start

        # Send calibration commands
        for cmd in cal_commands:
            await ctx.send_calibration_command(cmd)
            await asyncio.sleep(0.01)  # Let device process

        # Shutdown
        ctx.request_shutdown()
        await device_task

        return ctx, gpio

    async def _run_device_with_mixed_commands(
        self, commands: list[tuple[str, str]], *, homing: bool = False
    ) -> tuple[FakeDeviceContext, FakeGpio]:
        """Run the cover device with a mix of regular and calibration commands.

        Args:
            commands: List of (type, payload) where type is 'command' or 'calibrate'
        """
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=homing)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Start device as task
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)  # Let device start

        # Send commands
        for cmd_type, payload in commands:
            if cmd_type == "calibrate":
                await ctx.send_calibration_command(payload)
            else:
                await ctx.send_command(payload)
            await asyncio.sleep(0.01)  # Let device process

        # Shutdown
        ctx.request_shutdown()
        await device_task

        return ctx, gpio

    async def test_start_publishes_ready_state(self) -> None:
        """Calibration start transitions to READY and publishes state.

        Technique: State Transition Testing — IDLE -> READY.
        """
        # Act
        ctx, _gpio = await self._run_device_with_calibration_commands(
            ['{"phase": "start"}']
        )

        # Assert - initial state + calibration state
        assert len(ctx.published_channels) >= 1
        cal_publications = [
            (ch, payload)
            for ch, payload in ctx.published_channels
            if ch == "calibrate/state"
        ]
        assert len(cal_publications) >= 1
        channel, payload = cal_publications[0]
        assert channel == "calibrate/state"
        data = json.loads(payload)
        assert data["state"] == "READY"
        assert data["run"] == 1
        assert data["direction"] == "OPEN"

    async def test_go_presses_button_and_publishes_timing_offset(self) -> None:
        """Go transitions to TIMING_OFFSET, presses direction button.

        Technique: State Transition Testing — READY -> TIMING_OFFSET.
        Default starting_state='closed' means first direction is OPEN (up pin).
        """
        # Act
        ctx, gpio = await self._run_device_with_calibration_commands(
            ['{"phase": "start"}', '{"phase": "go"}']
        )

        # Assert — presses up pin (first direction is OPEN)
        assert any(p.pin == 17 for p in gpio.presses)  # up pin
        cal_publications = [
            payload for ch, payload in ctx.published_channels if ch == "calibrate/state"
        ]
        states = [json.loads(p)["state"] for p in cal_publications]
        assert "TIMING_OFFSET" in states

    async def test_start_with_starting_state_open_presses_down_pin(self) -> None:
        """starting_state='open' wires through: first direction CLOSE, go presses down pin.

        Technique: Specification-based — starting_state parameter end-to-end wiring.
        """
        # Act
        ctx, gpio = await self._run_device_with_calibration_commands(
            ['{"phase": "start", "starting_state": "open"}', '{"phase": "go"}']
        )

        # Assert — first direction is CLOSE, go presses down pin
        cal_publications = [
            payload for ch, payload in ctx.published_channels if ch == "calibrate/state"
        ]
        first_state = json.loads(cal_publications[0])
        assert first_state["direction"] == "CLOSE"

        # Should press down pin for CLOSE direction
        assert any(p.pin == 22 for p in gpio.presses)  # down

    async def test_normal_commands_blocked_during_calibration(self) -> None:
        """Normal cover commands are rejected during active calibration.

        Technique: Error Guessing — concurrent command during calibration.
        """
        # Act
        ctx, gpio = await self._run_device_with_mixed_commands(
            [
                ("calibrate", '{"phase": "start"}'),
                ("command", "open"),  # This should be blocked during calibration
            ]
        )

        # Assert — no GPIO presses from the "open" command
        # Only calibration-related presses should be present
        open_presses = [p for p in gpio.presses if p.pin == 17]  # up pin for open
        assert len(open_presses) == 0

    async def test_cancel_returns_to_idle(self) -> None:
        """Cancel from any state returns to IDLE, normal commands work again.

        Technique: State Transition Testing — cancel exits cleanly.
        """
        # Act
        ctx, gpio = await self._run_device_with_mixed_commands(
            [
                ("calibrate", '{"phase": "start"}'),
                ("calibrate", '{"phase": "cancel"}'),
                ("command", "open"),  # Should work after cancel
            ]
        )

        # Assert — publishes IDLE state and processes normal command
        cal_publications = [
            payload for ch, payload in ctx.published_channels if ch == "calibrate/state"
        ]
        states = [json.loads(p)["state"] for p in cal_publications]
        assert "IDLE" in states

        # Normal open command should work after cancel
        assert any(p.pin == 17 for p in gpio.presses)  # up pin

    async def test_invalid_transition_logs_warning_no_state_publish(self) -> None:
        """Unexpected action without a prior 'start' is logged, no MQTT published.

        Technique: Error Guessing — go() before start, sub_entity never entered.
        """
        # Act — go without start
        ctx, _gpio = await self._run_device_with_calibration_commands(
            ['{"phase": "go"}']
        )

        # Assert — no calibration state published (sub_entity was never entered)
        cal_publications = [
            payload for ch, payload in ctx.published_channels if ch == "calibrate/state"
        ]
        assert len(cal_publications) == 0

    def test_parse_calibrate_extracts_measure_dead_band(self) -> None:
        """Parse extracts measure_dead_band flag."""
        result = _parse_calibrate('{"phase": "start", "measure_dead_band": true}')
        assert result is not None
        assert result["measure_dead_band"] is True

        result = _parse_calibrate('{"phase": "start", "measure_dead_band": false}')
        assert result is not None
        assert result["measure_dead_band"] is False

    def test_parse_calibrate_extracts_measure_offset(self) -> None:
        """Parse extracts measure_offset flag."""
        result = _parse_calibrate('{"phase": "start", "measure_offset": false}')
        assert result is not None
        assert result["measure_offset"] is False

    async def test_sub_entity_exits_after_cancel(self) -> None:
        """Sub-entity availability goes offline after calibration is cancelled.

        Technique: Specification-based — sub_entity lifecycle exits on cancel.
        """
        # Act
        ctx, _gpio = await self._run_device_with_mixed_commands(
            [
                ("calibrate", '{"phase": "start"}'),
                ("calibrate", '{"phase": "cancel"}'),
            ]
        )

        # Assert — sub_entity should no longer be active after cancel
        assert "calibrate" not in ctx._active_sub_entities

    async def test_sub_entity_exits_on_device_shutdown_mid_calibration(self) -> None:
        """Sub-entity is cleaned up when device shuts down mid-calibration.

        Technique: Error Guessing — shutdown during active calibration.
        """
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        device_fn = make_cover(_DEFAULT_COVER, settings)
        ctx = FakeDeviceContext(gpio)

        # Start device
        device_task = asyncio.create_task(device_fn(ctx))
        await asyncio.sleep(0.01)

        # Begin calibration
        await ctx.send_calibration_command('{"phase": "start"}')
        await asyncio.sleep(0.05)  # Let calibration start

        # Shutdown while calibration is active
        ctx.request_shutdown()
        await device_task

        # Assert — sub_entity should be cleaned up after device shutdown
        assert "calibrate" not in ctx._active_sub_entities

    async def test_invalid_active_phase_does_not_refresh_timeout(self) -> None:
        """Out-of-sequence active phases do not keep calibration alive indefinitely.

        Technique: Error Guessing — repeated no-op phases during active calibration.

        Design note: we replace ``cover_module.time_module`` *directly* rather
        than using ``patch("velux2mqtt.devices.cover.time_module.monotonic")``.
        The reason is that ``time_module`` is an alias for the standard ``time``
        module, so patching its ``monotonic`` attribute is equivalent to
        patching ``time.monotonic`` globally — which also affects
        ``asyncio``'s internal ``loop.time()`` calls (two of them are made by
        ``asyncio.wait_for`` / ``asyncio.timeout`` setup before the session
        even starts).  Those hidden calls would consume mock values intended
        for the session's own deadline arithmetic, causing ``deadline`` to be
        computed from a "future" timestamp (121.0) and producing a deadline of
        241.0 s rather than 120.0 s.  The result is an infinite loop that can
        only be killed by the OS, crashing the IDE test runner.

        By swapping the module reference instead, only calls made through
        ``cover_module.time_module.monotonic`` are intercepted; asyncio's
        internal clock remains unaffected.
        """
        import logging

        import velux2mqtt.devices.cover as cover_module

        # Arrange
        gpio = FakeGpio()
        settings = _make_settings(enable_homing=False)
        ctx = FakeDeviceContext(gpio)
        calibration = CalibrationStateMachine()
        calibration.start()
        cal_queue = RepeatingCalibrationQueue("start")

        # Three calls happen in the production code:
        #   1. deadline = time_module.monotonic() + 120.0  → 0.0
        #   2. remaining = 120.0 - time_module.monotonic() → 0.0   (remaining = 120.0)
        #   3. remaining = 120.0 - time_module.monotonic() → 121.0 (remaining = -1.0 → exit)
        monotonic_values = iter([0.0, 0.0, 121.0])

        class _FakeTimeModule:
            @staticmethod
            def monotonic() -> float:
                return next(monotonic_values, 121.0)

        original_time_module = cover_module.time_module
        cover_module.time_module = _FakeTimeModule()  # type: ignore[assignment]
        try:
            async with ctx.sub_entity("calibrate") as cal:
                # Act — no outer wait_for needed; the fake clock drives the exit
                await _run_active_calibration_session(
                    ctx=ctx,
                    gpio=gpio,
                    cover_cfg=_DEFAULT_COVER,
                    settings=settings,
                    calibration=calibration,
                    cal=cal,
                    cal_queue=cal_queue,  # type: ignore[arg-type]
                    logger=logging.getLogger("test"),
                )
        finally:
            cover_module.time_module = original_time_module  # type: ignore[assignment]

        # Assert — the session cancelled due to deadline expiry, not a valid transition
        assert calibration.state.name == "IDLE"
        cal_states = [
            json.loads(payload)["state"]
            for ch, payload in ctx.published_channels
            if ch == "calibrate/state"
        ]
        assert cal_states[-1] == "IDLE"

    # Note: More complex calibration integration tests are covered by
    # integration tests. These unit tests focus on the basic command flow.


# ---------------------------------------------------------------------------
# Dead band tests
# ---------------------------------------------------------------------------

_DEAD_BAND_COVER = CoverConfig(
    name="window",
    pin_up=17,
    pin_stop=27,
    pin_down=22,
    travel_duration_up=20.0,
    travel_duration_down=20.0,
    travel_time_offset=1.0,
    max_timer_margin=2.0,
    dead_band_pct=10.0,  # 10% of total = (0.1/0.9)*20 ≈ 2.222s
)


class TestDeadBandTime:
    """Test dead band time calculation."""

    def test_dead_band_time_up(self) -> None:
        """Dead band time for up direction uses travel_duration_up.

        Technique: Specification-based — formula verification.
        """
        result = _dead_band_time(_DEAD_BAND_COVER, "up")
        assert result == pytest.approx(2.222, abs=0.01)  # (0.1/0.9)*20

    def test_dead_band_time_down(self) -> None:
        """Dead band time for down direction uses travel_duration_down.

        Technique: Specification-based — formula verification.
        """
        result = _dead_band_time(_DEAD_BAND_COVER, "down")
        assert result == pytest.approx(2.222, abs=0.01)  # (0.1/0.9)*20

    def test_dead_band_time_zero_when_disabled(self) -> None:
        """Dead band time is 0 when dead_band_pct is 0.

        Technique: Boundary Value Analysis — disabled dead band.
        """
        result = _dead_band_time(_DEFAULT_COVER, "up")
        assert result == 0.0

    def test_dead_band_time_asymmetric(self) -> None:
        """Dead band time differs for up/down with asymmetric travel durations.

        Technique: Equivalence Partitioning — asymmetric travel.
        """
        cover = CoverConfig(
            name="test",
            pin_up=1,
            pin_stop=2,
            pin_down=3,
            travel_duration_up=20.0,
            travel_duration_down=10.0,
            dead_band_pct=10.0,
        )
        assert _dead_band_time(cover, "up") == pytest.approx(2.222, abs=0.01)
        assert _dead_band_time(cover, "down") == pytest.approx(1.111, abs=0.01)


class TestExecuteStepDeadBand:
    """Test dead band traversal in _execute_step."""

    async def test_opening_from_zero_with_dead_band_presses_up_once(self) -> None:
        """Opening from 0% with dead band presses up pin once (not twice).

        The dead band and effective movement are one continuous motion.

        Technique: Specification-based — single button press for dead band + move.
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
            cover_cfg=_DEAD_BAND_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — up pin pressed once (for dead band), then stop
        up_presses = [p for p in gpio.presses if p.pin == 17]
        assert len(up_presses) == 1  # single press covers dead band + movement

    async def test_opening_from_nonzero_no_dead_band(self) -> None:
        """Opening from non-zero position skips dead band traversal.

        Technique: Equivalence Partitioning — dead band only applies from 0%.
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
        step = MoveStep(target=100)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEAD_BAND_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — endpoint move skips STOP (motor stalls at limit)
        assert len(gpio.presses) == 1
        assert gpio.presses[0].pin == 17  # up only

    async def test_closing_to_zero_with_dead_band(self) -> None:
        """Closing to 0% with dead band waits extra time for handle closure.

        Technique: Specification-based — dead band traversal on close.
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
        step = MoveStep(target=0)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEAD_BAND_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — endpoint move skips STOP; dead band wait still happens
        assert len(gpio.presses) == 1
        assert gpio.presses[0].pin == 22  # down only
        assert tracker.position == 0.0

    async def test_closing_to_nonzero_no_dead_band(self) -> None:
        """Closing to non-zero position skips dead band traversal.

        Technique: Equivalence Partitioning — dead band only applies to 0%.
        """
        # Arrange
        gpio = FakeGpio()
        ctx = FakeDeviceContext(gpio)
        settings = _make_settings()
        tracker = PositionTracker(
            travel_duration_up=20.0,
            travel_duration_down=20.0,
        )
        tracker.position = 80.0
        step = MoveStep(target=30)

        # Act
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEAD_BAND_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — normal down then stop
        assert gpio.presses[0].pin == 22  # down
        assert gpio.presses[1].pin == 27  # stop

    async def test_no_dead_band_when_disabled(self) -> None:
        """No dead band traversal when dead_band_pct is 0.

        Technique: Boundary Value Analysis — disabled dead band.
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

        # Act (using _DEFAULT_COVER which has dead_band_pct=0)
        await _execute_step(
            ctx=ctx,
            gpio=gpio,
            cover_cfg=_DEFAULT_COVER,
            settings=settings,
            tracker=tracker,
            step=step,
            logger=__import__("logging").getLogger("test"),
        )

        # Assert — endpoint move skips STOP (motor stalls at limit)
        assert len(gpio.presses) == 1
        assert gpio.presses[0].pin == 17  # up only
