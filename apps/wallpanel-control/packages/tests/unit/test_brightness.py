"""Unit tests for devices/brightness.py — brightness command handler.

Test Techniques Used:
- Equivalence Partitioning: brightness 0 (screen-off path), 1-99 (midrange),
  100 (full brightness) as distinct behaviour classes.
- Boundary Value Analysis: 0, 1, 50, 100 at the edges of the 0-100 range;
  -1 and 101 just outside.
- State Transition Testing: screen off → screen on when brightness > 0.
- Error Guessing: non-integer payload raises ValueError; out-of-range raises
  ValueError; unreachable wallpanel returns None (suppresses publish).
- Specification-based Testing: BrightnessState defaults, lazy max_brightness
  initialization and caching, create_brightness_state factory.
"""

from __future__ import annotations

import pytest

from wallpanel_control.adapters.fake import FakeWallpanel
from wallpanel_control.devices.brightness import (
    BrightnessState,
    create_brightness_state,
    handle_brightness,
    router,
)
from wallpanel_control.ports import WallpanelUnreachableError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(max_brightness: int | None = 7812) -> BrightnessState:
    return BrightnessState(max_brightness=max_brightness)


# =============================================================================
# BrightnessState
# =============================================================================


@pytest.mark.unit
class TestBrightnessState:
    """Verify BrightnessState dataclass defaults and structure.

    Technique: Specification-based — constructor defaults match spec.
    """

    def test_last_known_brightness_defaults_to_none(self) -> None:
        """last_known_brightness starts as None before any command."""
        state = BrightnessState()

        assert state.last_known_brightness is None

    def test_max_brightness_defaults_to_none(self) -> None:
        """max_brightness starts as None (lazily read at first command time)."""
        state = BrightnessState()

        assert state.max_brightness is None

    def test_max_brightness_stored(self) -> None:
        """max_brightness is stored as provided."""
        state = BrightnessState(max_brightness=1000)

        assert state.max_brightness == 1000


# =============================================================================
# create_brightness_state
# =============================================================================


@pytest.mark.unit
class TestCreateBrightnessState:
    """Verify factory returns an uninitialised BrightnessState.

    Technique: Specification-based — zero-arg sync factory.
    """

    def test_returns_brightness_state_instance(self) -> None:
        """Factory returns a BrightnessState instance."""
        state = create_brightness_state()

        assert isinstance(state, BrightnessState)

    def test_max_brightness_is_none(self) -> None:
        """max_brightness is None — lazily read at first command time."""
        state = create_brightness_state()

        assert state.max_brightness is None

    def test_last_known_brightness_initially_none(self) -> None:
        """Factory always returns state with last_known_brightness=None."""
        state = create_brightness_state()

        assert state.last_known_brightness is None


# =============================================================================
# handle_brightness — payload parsing / validation
# =============================================================================


@pytest.mark.unit
class TestHandleBrightnessValidation:
    """Verify payload validation raises ValueError for invalid input.

    Technique: Error Guessing + Equivalence Partitioning.
    """

    async def test_non_integer_payload_raises_value_error(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Non-integer string raises ValueError (not published)."""
        # Arrange
        state = _state()

        # Act / Assert
        with pytest.raises(ValueError):
            await handle_brightness("abc", fake_wallpanel, state)

    async def test_negative_value_raises_value_error(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Value -1 is below lower boundary and raises ValueError.

        Technique: Boundary Value Analysis — just below 0.
        """
        state = _state()

        with pytest.raises(ValueError):
            await handle_brightness("-1", fake_wallpanel, state)

    async def test_value_above_100_raises_value_error(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Value 101 is above upper boundary and raises ValueError.

        Technique: Boundary Value Analysis — just above 100.
        """
        state = _state()

        with pytest.raises(ValueError):
            await handle_brightness("101", fake_wallpanel, state)

    async def test_empty_payload_raises_value_error(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Empty string raises ValueError (int() conversion fails)."""
        state = _state()

        with pytest.raises(ValueError):
            await handle_brightness("", fake_wallpanel, state)


# =============================================================================
# handle_brightness — brightness == 0 (screen off path)
# =============================================================================


@pytest.mark.unit
class TestHandleBrightnessZero:
    """Verify brightness 0 turns screen off and returns correct payload.

    Technique: Specification-based + State Transition (screen on → off).
    """

    async def test_brightness_0_calls_screen_off(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Brightness 0 calls screen_off on the wallpanel."""
        # Arrange
        fake_wallpanel.screen_state = True
        state = _state()

        # Act
        await handle_brightness("0", fake_wallpanel, state)

        # Assert
        assert fake_wallpanel.screen_state is False

    async def test_brightness_0_returns_brightness_dict(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Brightness 0 returns {"brightness": 0}."""
        # Arrange
        state = _state()

        # Act
        result = await handle_brightness("0", fake_wallpanel, state)

        # Assert
        assert result == {"brightness": 0}

    async def test_brightness_0_updates_last_known_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Brightness 0 sets state.last_known_brightness to 0."""
        # Arrange
        state = _state()

        # Act
        await handle_brightness("0", fake_wallpanel, state)

        # Assert
        assert state.last_known_brightness == 0


# =============================================================================
# handle_brightness — screen off + brightness > 0 (screen on first)
# =============================================================================


@pytest.mark.unit
class TestHandleBrightnessScreenOn:
    """Verify screen is turned on before applying brightness when off.

    Technique: State Transition Testing — screen_state: False → True.
    """

    async def test_screen_off_then_brightness_turns_screen_on(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """When screen is off and brightness > 0, screen_on is called first."""
        # Arrange
        fake_wallpanel.screen_state = False
        state = _state()

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert
        assert fake_wallpanel.screen_state is True

    async def test_screen_already_on_not_toggled(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """When screen is already on, screen_on is not called redundantly."""
        # Arrange
        fake_wallpanel.screen_state = True
        initial_brightness = fake_wallpanel.brightness
        state = _state()

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert — brightness was set (screen_on not called means no state reset)
        assert fake_wallpanel.screen_state is True
        assert fake_wallpanel.brightness != initial_brightness


# =============================================================================
# handle_brightness — raw value calculation
# =============================================================================


@pytest.mark.unit
class TestHandleBrightnessRawCalculation:
    """Verify raw brightness scaling uses max_brightness correctly.

    Technique: Equivalence Partitioning + Boundary Value Analysis.
    """

    async def test_brightness_50_calculates_correct_raw_value(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """50% maps to round(max_brightness * 50 / 100).

        With default max_brightness=7812: round(7812 * 50 / 100) = 3906.
        """
        # Arrange
        state = _state(max_brightness=7812)

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert
        assert fake_wallpanel.brightness == round(7812 * 50 / 100)

    async def test_brightness_100_uses_full_max_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """100% maps to exactly max_brightness (round(max * 100 / 100) = max)."""
        # Arrange
        state = _state(max_brightness=7812)

        # Act
        await handle_brightness("100", fake_wallpanel, state)

        # Assert
        assert fake_wallpanel.brightness == 7812

    async def test_brightness_50_custom_max(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """50% scales relative to state.max_brightness (not a global constant)."""
        # Arrange
        state = _state(max_brightness=1000)

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert
        assert fake_wallpanel.brightness == 500

    async def test_brightness_positive_returns_percentage_dict(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Non-zero brightness returns {"brightness": <percentage>}."""
        # Arrange
        state = _state()

        # Act
        result = await handle_brightness("75", fake_wallpanel, state)

        # Assert
        assert result == {"brightness": 75}

    async def test_brightness_updates_last_known_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Successful command updates state.last_known_brightness."""
        # Arrange
        state = _state()

        # Act
        await handle_brightness("42", fake_wallpanel, state)

        # Assert
        assert state.last_known_brightness == 42


# =============================================================================
# handle_brightness — unreachable wallpanel
# =============================================================================


@pytest.mark.unit
class TestHandleBrightnessUnreachable:
    """Verify unreachable wallpanel suppresses publish (returns None) and logs warning.

    Technique: Error Guessing — WallpanelUnreachableError and get_screen_state=None.
    """

    async def test_unreachable_returns_none(self) -> None:
        """Unreachable wallpanel (WallpanelUnreachableError) returns None."""
        # Arrange
        fake = FakeWallpanel(reachable=False)
        state = _state()

        # Act
        result = await handle_brightness("50", fake, state)

        # Assert
        assert result is None

    async def test_unreachable_returns_none_for_brightness_0(self) -> None:
        """Unreachable wallpanel returns None even for brightness=0.

        screen_off() raises WallpanelUnreachableError when unreachable.
        """
        # Arrange
        fake = FakeWallpanel(reachable=False)
        state = _state()

        # Act
        result = await handle_brightness("0", fake, state)

        # Assert
        assert result is None

    async def test_brightness_0_logs_warning_on_wallpanel_unreachable(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """WallpanelUnreachableError from screen_off() logs a warning.

        Technique: Error Guessing — offline panel aborts screen-off path gracefully.
        """
        import logging

        # Arrange
        fake = FakeWallpanel(reachable=False)
        state = _state()

        # Act
        with caplog.at_level(
            logging.WARNING, logger="wallpanel_control.devices.brightness"
        ):
            result = await handle_brightness("0", fake, state)

        # Assert
        assert result is None
        assert "unreachable" in caplog.text.lower()

    async def test_positive_brightness_logs_warning_on_wallpanel_unreachable(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """WallpanelUnreachableError from set_brightness() logs a warning.

        Technique: Error Guessing — offline panel aborts set-brightness path gracefully.
        """
        import logging

        # Arrange: screen is on so we skip screen_on(), but set_brightness raises
        class _FailOnSetBrightness(FakeWallpanel):
            async def set_brightness(self, value: int) -> None:
                raise WallpanelUnreachableError("gone offline during set")

        fake = _FailOnSetBrightness(screen_state=True)
        state = _state()

        # Act
        with caplog.at_level(
            logging.WARNING, logger="wallpanel_control.devices.brightness"
        ):
            result = await handle_brightness("50", fake, state)

        # Assert
        assert result is None
        assert "unreachable" in caplog.text.lower()

    async def test_get_screen_state_none_returns_none(self) -> None:
        """get_screen_state() returning None is treated as unreachable."""

        # Arrange: custom fake that reports screen_state=None (hibernating)
        class _NullScreenState(FakeWallpanel):
            async def get_screen_state(self) -> bool | None:
                return None

        fake = _NullScreenState()
        state = _state()

        # Act
        result = await handle_brightness("50", fake, state)

        # Assert
        assert result is None


# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router exports the brightness command.

    Technique: Specification-based — public registered_names API.
    """

    def test_brightness_command_registered(self) -> None:
        """Router.registered_names includes 'brightness'."""
        assert "brightness" in router.registered_names

    def test_brightness_init_is_create_brightness_state(self) -> None:
        """Command registration uses create_brightness_state as init factory."""
        cmd = next(r for r in router._commands if r.name == "brightness")

        assert cmd.init is create_brightness_state


# =============================================================================
# handle_brightness — lazy max_brightness initialisation
# =============================================================================


@pytest.mark.unit
class TestLazyMaxBrightness:
    """Verify max_brightness is read lazily on first non-zero brightness command.

    Technique: State Transition Testing — None → int on first command.
    """

    async def test_first_nonzero_reads_max_brightness(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """First non-zero command sets state.max_brightness from wallpanel."""
        # Arrange
        state = BrightnessState()  # max_brightness=None

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert
        assert state.max_brightness == fake_wallpanel.max_brightness

    async def test_max_brightness_cached_after_first_read(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Second non-zero command does not re-read max_brightness.

        Technique: State Caching — value fixed after first successful read.
        """
        # Arrange
        state = BrightnessState()
        await handle_brightness("50", fake_wallpanel, state)
        original = state.max_brightness
        # Change the fake's value so a second read would give a different result
        fake_wallpanel.max_brightness = 9999

        # Act
        await handle_brightness("50", fake_wallpanel, state)

        # Assert: cached value unchanged, 9999 not read
        assert state.max_brightness == original
        assert state.max_brightness != 9999

    async def test_unreachable_during_lazy_read_returns_none(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Unreachable wallpanel during lazy max_brightness read returns None.

        Technique: Error Guessing — get_max_brightness raises on unreachable panel.
        """
        import logging

        # Arrange
        fake = FakeWallpanel(reachable=False)
        state = BrightnessState()  # max_brightness=None triggers lazy read

        # Act
        with caplog.at_level(
            logging.WARNING, logger="wallpanel_control.devices.brightness"
        ):
            result = await handle_brightness("50", fake, state)

        # Assert
        assert result is None
        assert "unreachable" in caplog.text.lower()
