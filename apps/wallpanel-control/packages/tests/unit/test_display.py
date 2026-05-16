"""Unit tests for devices/display.py — display command handler.

Test Techniques Used:
- Specification-based Testing: DisplayCommand/DisplayState Pydantic contracts,
    _poll_display_state behaviour, _execute_display_command behaviour,
    router registration.
- Equivalence Partitioning: state="on", state="off", brightness-only as
    distinct valid command classes; unreachable as a separate partition.
- Boundary Value Analysis: brightness_percent 1, 100, 0 (invalid), 101 (invalid).
- Branch/Condition Coverage: all four valid command combinations, unreachable
    paths, max_brightness zero guard, None returns from brightness/screen.
- State Transition Testing: screen off → on when brightness-only command arrives.
- Error Guessing: empty payload, unknown extra field, state+brightness when
    state="off", missing both fields.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

import pytest
from pydantic import ValidationError

from wallpanel_control.adapters.fake import FakeWallpanel
from wallpanel_control.devices.display import (
    DisplayCommand,
    DisplayState,
    _DisplayHandlerState,
    _UNAVAILABLE,
    _execute_display_command,
    _poll_display_state,
    create_display_handler_state,
    handle_display,
    router,
)
from wallpanel_control.ports import WallpanelUnreachableError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(max_brightness: int | None = 7812) -> _DisplayHandlerState:
    return _DisplayHandlerState(max_brightness=max_brightness)


class _StubWallpanel:
    """Base wallpanel stub for edge-case polling tests."""

    async def is_reachable(self) -> bool:
        return True

    async def get_max_brightness(self) -> int:
        return 7812

    async def get_brightness(self) -> int | None:
        return 7812

    async def get_screen_state(self) -> bool | None:
        return True

    async def set_brightness(self, value: int) -> None:  # noqa: ARG002
        ...

    async def screen_on(self) -> None: ...

    async def screen_off(self) -> None: ...

    async def hibernate(self) -> None: ...

    async def suspend(self) -> None: ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...


class _BrightnessNoneStub(_StubWallpanel):
    """Stub returning None from get_brightness (simulates TOCTOU unreachable)."""

    async def get_brightness(self) -> int | None:
        return None


class _BrightnessRaisesStub(_StubWallpanel):
    """Stub raising WallpanelUnreachableError from get_brightness."""

    async def get_brightness(self) -> int | None:
        raise WallpanelUnreachableError("gone")


# =============================================================================
# DisplayCommand — validation
# =============================================================================


@pytest.mark.unit
class TestDisplayCommandValidation:
    """Verify DisplayCommand Pydantic validation rules.

    Technique: Equivalence Partitioning + Boundary Value Analysis.
    """

    def test_state_on_only_is_valid(self) -> None:
        """state='on' with no brightness is a valid command."""
        cmd = DisplayCommand(state="on")
        assert cmd.state == "on"
        assert cmd.brightness_percent is None

    def test_state_off_only_is_valid(self) -> None:
        """state='off' with no brightness is a valid command."""
        cmd = DisplayCommand(state="off")
        assert cmd.state == "off"
        assert cmd.brightness_percent is None

    def test_brightness_only_is_valid(self) -> None:
        """brightness_percent only (no state) is a valid command."""
        cmd = DisplayCommand(brightness_percent=60)
        assert cmd.state is None
        assert cmd.brightness_percent == 60

    def test_state_on_with_brightness_is_valid(self) -> None:
        """state='on' combined with brightness_percent is valid."""
        cmd = DisplayCommand(state="on", brightness_percent=80)
        assert cmd.state == "on"
        assert cmd.brightness_percent == 80

    def test_empty_payload_raises_validation_error(self) -> None:
        """Empty dict (no fields) is rejected — at least one required.

        Technique: Error Guessing — misuse of the API.
        """
        with pytest.raises(ValidationError, match="brightness_percent"):
            DisplayCommand()

    def test_state_off_with_brightness_raises_validation_error(self) -> None:
        """state='off' combined with brightness_percent is rejected.

        Technique: Specification-based — ambiguous combination.
        """
        with pytest.raises(ValidationError, match="brightness_percent"):
            DisplayCommand(state="off", brightness_percent=50)

    def test_unknown_field_raises_validation_error(self) -> None:
        """Extra unknown fields are rejected (extra='forbid').

        Technique: Specification-based — strict payload contract.
        """
        with pytest.raises(ValidationError):
            DisplayCommand.model_validate({"unknown_field": 1, "state": "on"})

    def test_brightness_zero_is_rejected(self) -> None:
        """brightness_percent=0 is below the minimum of 1.

        Technique: Boundary Value Analysis — just below valid range.
        """
        with pytest.raises(ValidationError):
            DisplayCommand(brightness_percent=0)

    def test_brightness_101_is_rejected(self) -> None:
        """brightness_percent=101 is above the maximum of 100.

        Technique: Boundary Value Analysis — just above valid range.
        """
        with pytest.raises(ValidationError):
            DisplayCommand(brightness_percent=101)

    def test_brightness_1_is_valid(self) -> None:
        """brightness_percent=1 is the minimum valid value.

        Technique: Boundary Value Analysis — lower boundary.
        """
        cmd = DisplayCommand(brightness_percent=1)
        assert cmd.brightness_percent == 1

    def test_brightness_100_is_valid(self) -> None:
        """brightness_percent=100 is the maximum valid value.

        Technique: Boundary Value Analysis — upper boundary.
        """
        cmd = DisplayCommand(brightness_percent=100)
        assert cmd.brightness_percent == 100

    def test_invalid_state_value_raises_validation_error(self) -> None:
        """state='ON' (uppercase) is rejected — Literal requires exact case.

        Technique: Error Guessing — old API used uppercase.
        """
        with pytest.raises(ValidationError):
            DisplayCommand(state="ON")  # type: ignore[arg-type]


# =============================================================================
# DisplayState — model
# =============================================================================


@pytest.mark.unit
class TestDisplayState:
    """Verify DisplayState model.

    Technique: Specification-based — output contract.
    """

    def test_available_state_on(self) -> None:
        """Reachable state with screen on serialises correctly."""
        s = DisplayState(available=True, state="on", brightness_percent=75)
        assert s.model_dump() == {
            "available": True,
            "state": "on",
            "brightness_percent": 75,
        }

    def test_unavailable_state(self) -> None:
        """Unavailable state uses null for state and brightness_percent."""
        s = _UNAVAILABLE
        assert s.available is False
        assert s.state is None
        assert s.brightness_percent is None

    def test_brightness_percent_zero_is_valid_in_output(self) -> None:
        """brightness_percent=0 is valid in DisplayState (screen off or fully dim).

        Technique: Boundary Value Analysis — output lower bound distinct from
        command input which rejects 0.
        """
        s = DisplayState(available=True, state="off", brightness_percent=0)
        assert s.brightness_percent == 0


# =============================================================================
# _poll_display_state — polling logic
# =============================================================================


@pytest.mark.unit
class TestPollDisplayState:
    """Verify _poll_display_state reads and normalises display state.

    Technique: Branch/Condition Coverage + State Transition.
    """

    async def test_unreachable_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """When wallpanel is unreachable, returns unavailable state."""
        fake_wallpanel.set_reachable(False)
        state = _state()

        result = await _poll_display_state(fake_wallpanel, state)

        assert result.available is False
        assert result.state is None
        assert result.brightness_percent is None

    async def test_reachable_returns_on_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Reachable wallpanel with screen on returns available=True, state='on'."""
        fake_wallpanel.screen_state = True
        fake_wallpanel.brightness = 3906  # 50% of 7812
        state = _state(max_brightness=7812)

        result = await _poll_display_state(fake_wallpanel, state)

        assert result.available is True
        assert result.state == "on"
        assert result.brightness_percent == 50

    async def test_reachable_returns_off_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Reachable wallpanel with screen off returns state='off'."""
        fake_wallpanel.screen_state = False
        fake_wallpanel.brightness = 0
        state = _state(max_brightness=7812)

        result = await _poll_display_state(fake_wallpanel, state)

        assert result.available is True
        assert result.state == "off"

    async def test_lazy_reads_max_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """max_brightness is lazily read and cached on first poll."""
        fake_wallpanel.max_brightness = 1000
        fake_wallpanel.brightness = 500
        state = _state(max_brightness=None)

        result = await _poll_display_state(fake_wallpanel, state)

        assert state.max_brightness == 1000
        assert result.brightness_percent == 50

    async def test_caches_max_brightness_across_polls(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """max_brightness is reused after the first successful read."""
        fake_wallpanel.max_brightness = 1000
        fake_wallpanel.brightness = 500
        state = _state(max_brightness=None)

        await _poll_display_state(fake_wallpanel, state)
        assert state.max_brightness == 1000

        # Change hardware max; if re-read, percent would be 25 instead of 50.
        fake_wallpanel.max_brightness = 2000

        result = await _poll_display_state(fake_wallpanel, state)

        assert state.max_brightness == 1000  # unchanged — cached
        assert result.brightness_percent == 50  # proves 1000 was used, not 2000

    async def test_max_brightness_zero_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Zero max_brightness returns unavailable (guard against division by zero).

        Technique: Error Guessing — degenerate hardware state.
        """
        fake_wallpanel.max_brightness = 0
        state = _state(max_brightness=None)

        result = await _poll_display_state(fake_wallpanel, state)

        assert result.available is False

    async def test_none_brightness_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """None from get_brightness (TOCTOU unreachable) returns unavailable."""
        result = await _poll_display_state(_BrightnessNoneStub(), _state())

        assert result.available is False

    async def test_wallpanel_unreachable_error_mid_poll_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """WallpanelUnreachableError mid-poll returns unavailable.

        Technique: Error Guessing — panel goes offline between is_reachable() and reads.
        """
        result = await _poll_display_state(
            _BrightnessRaisesStub(), _state(max_brightness=7812)
        )

        assert result.available is False


# =============================================================================
# _execute_display_command — command execution
# =============================================================================


@pytest.mark.unit
class TestExecuteDisplayCommandOff:
    """Verify state='off' turns screen off.

    Technique: Equivalence Partitioning — state='off' command class.
    """

    async def test_off_calls_screen_off(self, fake_wallpanel: FakeWallpanel) -> None:
        """state='off' calls screen_off on the wallpanel."""
        fake_wallpanel.screen_state = True
        state = _state()

        await _execute_display_command(
            DisplayCommand(state="off"), fake_wallpanel, state
        )

        assert fake_wallpanel.screen_state is False

    async def test_off_returns_off_state(self, fake_wallpanel: FakeWallpanel) -> None:
        """state='off' returns available=True, state='off'."""
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(state="off"), fake_wallpanel, state
        )

        assert result.available is True
        assert result.state == "off"

    async def test_off_includes_last_brightness_in_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='off' publishes observed brightness in the response."""
        fake_wallpanel.brightness = 500
        fake_wallpanel.max_brightness = 1000
        state = _state(max_brightness=1000)

        result = await _execute_display_command(
            DisplayCommand(state="off"), fake_wallpanel, state
        )

        assert result.brightness_percent == 50

    async def test_off_unreachable_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='off' when wallpanel unreachable returns unavailable state."""
        fake_wallpanel.set_reachable(False)
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(state="off"), fake_wallpanel, state
        )

        assert result.available is False


@pytest.mark.unit
class TestExecuteDisplayCommandOn:
    """Verify state='on' turns screen on.

    Technique: Equivalence Partitioning — state='on' command class.
    """

    async def test_on_calls_screen_on(self, fake_wallpanel: FakeWallpanel) -> None:
        """state='on' calls screen_on on the wallpanel."""
        fake_wallpanel.screen_state = False
        state = _state()

        await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert fake_wallpanel.screen_state is True

    async def test_on_returns_on_state(self, fake_wallpanel: FakeWallpanel) -> None:
        """state='on' returns available=True, state='on'."""
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert result.available is True
        assert result.state == "on"

    async def test_on_publishes_observed_brightness_when_no_brightness_given(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='on' only publishes current brightness, not cached intent."""
        fake_wallpanel.brightness = 500
        fake_wallpanel.max_brightness = 1000
        state = _state(max_brightness=1000)

        result = await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert result.brightness_percent == 50

    async def test_first_on_command_publishes_non_null_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """First state='on' command polls brightness instead of returning null.

        Technique: Error Guessing — no cached brightness exists yet.
        """
        fake_wallpanel.brightness = 250
        fake_wallpanel.max_brightness = 1000
        state = create_display_handler_state()

        result = await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert result.available is True
        assert result.state == "on"
        assert result.brightness_percent == 25

    async def test_on_command_ignores_stale_cached_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='on' publishes observed hardware brightness, not stale cache.

        Technique: Error Guessing — cached intent diverges from hardware state.
        """
        fake_wallpanel.brightness = 900
        fake_wallpanel.max_brightness = 1000
        state = _state(max_brightness=1000)

        result = await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert result.brightness_percent == 90

    async def test_on_unreachable_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='on' when wallpanel unreachable returns unavailable state.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(state="on"), fake_wallpanel, state
        )

        assert result.available is False


@pytest.mark.unit
class TestExecuteDisplayCommandBrightness:
    """Verify brightness_percent sets backlight and returns correct state.

    Technique: Equivalence Partitioning — brightness command class.
    """

    async def test_brightness_sets_raw_value(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """brightness_percent maps correctly to raw sysfs value."""
        fake_wallpanel.max_brightness = 1000
        fake_wallpanel.screen_state = True
        state = _state(max_brightness=1000)

        await _execute_display_command(
            DisplayCommand(brightness_percent=50), fake_wallpanel, state
        )

        assert fake_wallpanel.brightness == 500

    async def test_brightness_returns_on_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """brightness_percent returns available=True, state='on'."""
        fake_wallpanel.screen_state = True
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(brightness_percent=75), fake_wallpanel, state
        )

        assert result.available is True
        assert result.state == "on"
        assert result.brightness_percent == 75

    async def test_brightness_turns_screen_on_when_off(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """brightness_percent with screen off turns screen on first.

        Technique: State Transition — screen off → screen on.
        """
        fake_wallpanel.screen_state = False
        state = _state()

        await _execute_display_command(
            DisplayCommand(brightness_percent=60), fake_wallpanel, state
        )

        assert fake_wallpanel.screen_state is True

    async def test_brightness_unreachable_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Unreachable wallpanel returns unavailable state for brightness command."""
        fake_wallpanel.set_reachable(False)
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(brightness_percent=50), fake_wallpanel, state
        )

        assert result.available is False

    async def test_max_brightness_zero_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """max_brightness=0 suppresses the brightness command.

        Technique: Error Guessing — degenerate hardware state.
        """
        fake_wallpanel.max_brightness = 0
        fake_wallpanel.screen_state = True
        state = _state(max_brightness=None)

        result = await _execute_display_command(
            DisplayCommand(brightness_percent=50), fake_wallpanel, state
        )

        assert result.available is False


@pytest.mark.unit
class TestExecuteDisplayCommandOnWithBrightness:
    """Verify state='on' combined with brightness_percent.

    Technique: Equivalence Partitioning — combined command class.
    """

    async def test_on_with_brightness_turns_on_and_sets_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='on' + brightness_percent turns screen on then sets brightness."""
        fake_wallpanel.screen_state = False
        fake_wallpanel.max_brightness = 1000
        state = _state(max_brightness=1000)

        result = await _execute_display_command(
            DisplayCommand(state="on", brightness_percent=80), fake_wallpanel, state
        )

        assert fake_wallpanel.screen_state is True
        assert fake_wallpanel.brightness == 800
        assert result.available is True
        assert result.state == "on"
        assert result.brightness_percent == 80

    async def test_on_with_brightness_unreachable_returns_unavailable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """state='on' + brightness_percent when unreachable returns unavailable.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)
        state = _state()

        result = await _execute_display_command(
            DisplayCommand(state="on", brightness_percent=50), fake_wallpanel, state
        )

        assert result.available is False


# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router registers 'display' as a command.

    Technique: Specification-based — public API contract.
    """

    def test_display_in_registered_names(self) -> None:
        """Router has a command registered as 'display'."""
        assert "display" in router.registered_names

    def test_display_registered_as_command(self) -> None:
        """'display' is registered as a command (not a device).

        Technique: Structural — verifies archetype is command, not device.
        """
        command_names = {r.name for r in router._commands}
        assert "display" in command_names

    def test_display_command_init_factory(self) -> None:
        """Command init factory is create_display_handler_state.

        Technique: Structural — init factory creates per-invocation state.
        """
        reg = next(r for r in router._commands if r.name == "display")
        assert reg.init is create_display_handler_state

    def test_display_command_payload_model(self) -> None:
        """Command payload_model is DisplayCommand.

        Technique: Structural — payload_model drives AsyncAPI manifest schema.
        """
        reg = next(r for r in router._commands if r.name == "display")
        assert reg.payload_model is DisplayCommand

    def test_display_command_state_model(self) -> None:
        """Command state_model is DisplayState.

        Technique: Structural — state_model drives AsyncAPI manifest schema.
        """
        reg = next(r for r in router._commands if r.name == "display")
        assert reg.state_model is DisplayState


# =============================================================================
# create_display_handler_state — factory
# =============================================================================


@pytest.mark.unit
class TestCreateDisplayHandlerState:
    """Verify factory returns an uninitialised _DisplayHandlerState.

    Technique: Specification-based — explicit zero-arg factory for cosalette DI.
    """

    def test_returns_display_handler_state_instance(self) -> None:
        """Factory returns a _DisplayHandlerState instance."""
        state = create_display_handler_state()

        assert isinstance(state, _DisplayHandlerState)

    def test_max_brightness_initially_none(self) -> None:
        """max_brightness is None — lazily read at first command time."""
        state = create_display_handler_state()

        assert state.max_brightness is None


# =============================================================================
# handle_display — typed handler
# =============================================================================


@pytest.mark.unit
class TestHandleDisplay:
    """Verify handle_display returns typed DisplayState.

    Technique: Specification-based + Equivalence Partitioning.
    """

    async def test_returns_display_state_on_success(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """handle_display returns a DisplayState instance on success."""
        fake_wallpanel.screen_state = True
        state = create_display_handler_state()
        state.max_brightness = 7812

        result = await handle_display(
            cmd=DisplayCommand(state="on"),
            wallpanel=fake_wallpanel,
            state=state,
        )

        assert isinstance(result, DisplayState)
        assert result.available is True
        assert result.state == "on"

    async def test_returns_unavailable_when_unreachable(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """handle_display returns unavailable state when wallpanel is unreachable."""
        fake_wallpanel.set_reachable(False)
        state = create_display_handler_state()

        result = await handle_display(
            cmd=DisplayCommand(state="off"),
            wallpanel=fake_wallpanel,
            state=state,
        )

        assert isinstance(result, DisplayState)
        assert result.available is False

    async def test_brightness_command_returns_on_state(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """handle_display with brightness_percent returns state='on'."""
        fake_wallpanel.screen_state = True
        state = create_display_handler_state()
        state.max_brightness = 1000

        result = await handle_display(
            cmd=DisplayCommand(brightness_percent=75),
            wallpanel=fake_wallpanel,
            state=state,
        )

        assert isinstance(result, DisplayState)
        assert result.available is True
        assert result.state == "on"
        assert result.brightness_percent == 75
