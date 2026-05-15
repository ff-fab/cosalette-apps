"""Unit tests for devices/screen.py — screen on/off command handler.

Test Techniques Used:
- Equivalence Partitioning: ON and OFF as distinct valid input classes;
  invalid strings as a separate class.
- Boundary Value Analysis: Case variants ("on", "ON", "On"), whitespace
  padding ("  ON  ") as boundary of the normalisation step.
- Branch/Condition Coverage: ON path, OFF path, unreachable path,
  invalid payload path.
- Error Guessing: Empty string, mixed-case, arbitrary string, None-like
  values all outside the valid partition.
- Specification-based Testing: router registration, return shapes,
  None suppression on unreachable.
"""

from __future__ import annotations

import logging

import pytest

from wallpanel_control.adapters.fake import FakeWallpanel
from wallpanel_control.devices.screen import handle_screen, router

# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router exposes the expected command name.

    Technique: Specification-based — public API contract.
    """

    def test_screen_in_registered_names(self) -> None:
        """Router has a command registered as 'screen'."""
        assert "screen" in router.registered_names


# =============================================================================
# handle_screen — ON path
# =============================================================================


@pytest.mark.unit
class TestHandleScreenOn:
    """Verify ON payload turns the screen on.

    Technique: Equivalence Partitioning — ON input class.
    """

    async def test_on_calls_screen_on(self, fake_wallpanel: FakeWallpanel) -> None:
        """ON payload calls screen_on and sets FakeWallpanel.screen_state True."""
        # Arrange
        fake_wallpanel.screen_state = False

        # Act
        result = await handle_screen("ON", fake_wallpanel)

        # Assert
        assert fake_wallpanel.screen_state is True
        assert result == {"state": "ON"}

    async def test_on_lowercase_accepted(self, fake_wallpanel: FakeWallpanel) -> None:
        """Lowercase 'on' is accepted case-insensitively.

        Technique: Boundary Value Analysis — edge of normalisation.
        """
        # Arrange
        fake_wallpanel.screen_state = False

        # Act
        result = await handle_screen("on", fake_wallpanel)

        # Assert
        assert fake_wallpanel.screen_state is True
        assert result == {"state": "ON"}

    async def test_on_with_whitespace_accepted(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """'  ON  ' with leading/trailing whitespace is accepted.

        Technique: Boundary Value Analysis — whitespace stripping boundary.
        """
        # Arrange
        fake_wallpanel.screen_state = False

        # Act
        result = await handle_screen("  ON  ", fake_wallpanel)

        # Assert
        assert fake_wallpanel.screen_state is True
        assert result == {"state": "ON"}


# =============================================================================
# handle_screen — OFF path
# =============================================================================


@pytest.mark.unit
class TestHandleScreenOff:
    """Verify OFF payload turns the screen off.

    Technique: Equivalence Partitioning — OFF input class.
    """

    async def test_off_calls_screen_off(self, fake_wallpanel: FakeWallpanel) -> None:
        """OFF payload calls screen_off and sets FakeWallpanel.screen_state False."""
        # Arrange
        fake_wallpanel.screen_state = True

        # Act
        result = await handle_screen("OFF", fake_wallpanel)

        # Assert
        assert fake_wallpanel.screen_state is False
        assert result == {"state": "OFF"}

    async def test_off_mixedcase_accepted(self, fake_wallpanel: FakeWallpanel) -> None:
        """Mixed-case 'Off' is accepted case-insensitively.

        Technique: Boundary Value Analysis — edge of normalisation.
        """
        # Arrange
        fake_wallpanel.screen_state = True

        # Act
        result = await handle_screen("Off", fake_wallpanel)

        # Assert
        assert fake_wallpanel.screen_state is False
        assert result == {"state": "OFF"}

    async def test_off_with_whitespace_accepted(
        self, fake_wallpanel: FakeWallpanel
    ) -> None:
        """'  off  ' with whitespace is accepted.

        Technique: Boundary Value Analysis — whitespace stripping boundary.
        """
        fake_wallpanel.screen_state = True
        result = await handle_screen("  off  ", fake_wallpanel)
        assert fake_wallpanel.screen_state is False
        assert result == {"state": "OFF"}


# =============================================================================
# handle_screen — unreachable path
# =============================================================================


@pytest.mark.unit
class TestHandleScreenUnreachable:
    """Verify unreachable wallpanel returns None and logs a warning.

    Technique: Error Guessing — WallpanelUnreachableError from hardware layer.
    """

    async def test_unreachable_returns_none(self) -> None:
        """WallpanelUnreachableError is caught and None is returned."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        result = await handle_screen("ON", fake)

        # Assert
        assert result is None

    async def test_unreachable_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """WallpanelUnreachableError triggers a WARNING log entry."""
        # Arrange
        fake = FakeWallpanel(reachable=False)

        # Act
        with caplog.at_level(
            logging.WARNING, logger="wallpanel_control.devices.screen"
        ):
            await handle_screen("ON", fake)

        # Assert
        assert caplog.records, "Expected at least one log record"
        assert any(r.levelno == logging.WARNING for r in caplog.records)


# =============================================================================
# handle_screen — invalid payload
# =============================================================================


@pytest.mark.unit
class TestHandleScreenInvalidPayload:
    """Verify invalid payloads raise ValueError.

    Technique: Equivalence Partitioning + Error Guessing — invalid input class.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "MAYBE",
            "1",
            "0",
            "true",
            "false",
            "",
            "  ",
            "on off",
        ],
    )
    async def test_invalid_payload_raises_value_error(
        self, payload: str, fake_wallpanel: FakeWallpanel
    ) -> None:
        """Any payload outside ON/OFF raises ValueError.

        Technique: Equivalence Partitioning — invalid partition mapped via
        parametrize.
        """
        with pytest.raises(ValueError):
            await handle_screen(payload, fake_wallpanel)
