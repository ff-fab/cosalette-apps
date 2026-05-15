"""Unit tests for devices/power.py — power command handler.

Test Techniques Used:
- Equivalence Partitioning: OFF, SLEEP, WAKE as distinct valid input classes;
  invalid strings as a separate class.
- Boundary Value Analysis: Case variants and whitespace padding as boundaries
  of the normalisation step.
- Branch/Condition Coverage: OFF path, SLEEP path, WAKE path, unreachable
  path (OFF and SLEEP), WAKE-despite-unreachable path, invalid payload path.
- Error Guessing: Empty string, mixed-case, arbitrary strings, extra whitespace.
- Specification-based Testing: router registration, return shapes, None
  suppression on unreachable for OFF/SLEEP, WoL call forwarding for WAKE.
"""

from __future__ import annotations

import logging

import pytest

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.devices.power import handle_power, router
from wallpanel_control.settings import WallpanelControlSettings

# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router exposes the expected command name.

    Technique: Specification-based — public API contract.
    """

    def test_power_in_registered_names(self) -> None:
        """Router has a command registered as 'power'."""
        assert "power" in router.registered_names


# =============================================================================
# handle_power — OFF path
# =============================================================================


@pytest.mark.unit
class TestHandlePowerOff:
    """Verify OFF payload hibernates the wallpanel.

    Technique: Equivalence Partitioning — OFF input class.
    """

    async def test_off_calls_hibernate(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """OFF payload calls hibernate and sets power_state to 'hibernating'."""
        # Act
        result = await handle_power("OFF", fake_wallpanel, fake_wol, wallpanel_settings)

        # Assert
        assert fake_wallpanel.power_state == "hibernating"
        assert fake_wallpanel.reachable is False
        assert result == {"state": "hibernating"}

    async def test_off_lowercase_accepted(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """Lowercase 'off' is accepted case-insensitively.

        Technique: Boundary Value Analysis — edge of normalisation.
        """
        result = await handle_power("off", fake_wallpanel, fake_wol, wallpanel_settings)

        assert fake_wallpanel.power_state == "hibernating"
        assert result == {"state": "hibernating"}

    async def test_off_with_whitespace_accepted(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """'  OFF  ' with whitespace is accepted.

        Technique: Boundary Value Analysis — whitespace stripping boundary.
        """
        result = await handle_power(
            "  OFF  ", fake_wallpanel, fake_wol, wallpanel_settings
        )

        assert result == {"state": "hibernating"}


# =============================================================================
# handle_power — SLEEP path
# =============================================================================


@pytest.mark.unit
class TestHandlePowerSleep:
    """Verify SLEEP payload suspends the wallpanel.

    Technique: Equivalence Partitioning — SLEEP input class.
    """

    async def test_sleep_calls_suspend(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """SLEEP payload calls suspend and sets power_state to 'suspended'."""
        # Act
        result = await handle_power(
            "SLEEP", fake_wallpanel, fake_wol, wallpanel_settings
        )

        # Assert
        assert fake_wallpanel.power_state == "suspended"
        assert fake_wallpanel.reachable is False
        assert result == {"state": "suspended"}

    async def test_sleep_lowercase_accepted(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """Lowercase 'sleep' is accepted case-insensitively.

        Technique: Boundary Value Analysis — edge of normalisation.
        """
        result = await handle_power(
            "sleep", fake_wallpanel, fake_wol, wallpanel_settings
        )

        assert fake_wallpanel.power_state == "suspended"
        assert result == {"state": "suspended"}

    async def test_sleep_with_whitespace_accepted(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """'  Sleep  ' with whitespace is accepted.

        Technique: Boundary Value Analysis — whitespace stripping boundary.
        """
        result = await handle_power(
            "  Sleep  ", fake_wallpanel, fake_wol, wallpanel_settings
        )

        assert result == {"state": "suspended"}


# =============================================================================
# handle_power — WAKE path
# =============================================================================


@pytest.mark.unit
class TestHandlePowerWake:
    """Verify WAKE payload sends a WoL packet.

    Technique: Equivalence Partitioning — WAKE input class.
    """

    async def test_wake_calls_wol(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
    ) -> None:
        """WAKE sends WoL with configured mac and broadcast, returns waking."""
        # Arrange
        settings = make_wallpanel_control_settings(
            wol_mac="DE:AD:BE:EF:00:01",
            wol_broadcast="192.168.1.255",
        )

        # Act
        result = await handle_power("WAKE", fake_wallpanel, fake_wol, settings)

        # Assert
        assert fake_wol.calls == [("DE:AD:BE:EF:00:01", "192.168.1.255")]
        assert result == {"state": "waking"}

    async def test_wake_uses_settings_defaults(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """WAKE uses wol_mac and wol_broadcast from settings."""
        # Act
        result = await handle_power(
            "WAKE", fake_wallpanel, fake_wol, wallpanel_settings
        )

        # Assert
        assert len(fake_wol.calls) == 1
        mac, broadcast = fake_wol.calls[0]
        assert mac == wallpanel_settings.wol_mac
        assert broadcast == wallpanel_settings.wol_broadcast
        assert result == {"state": "waking"}

    async def test_wake_when_wallpanel_unreachable(self, fake_wol: FakeWol) -> None:
        """WAKE succeeds even when wallpanel is unreachable.

        Technique: Error Guessing — WoL should not depend on SSH reachability.
        """
        # Arrange
        fake_unreachable = FakeWallpanel(reachable=False)
        settings = make_wallpanel_control_settings()

        # Act
        result = await handle_power("WAKE", fake_unreachable, fake_wol, settings)

        # Assert
        assert len(fake_wol.calls) == 1
        assert result == {"state": "waking"}

    async def test_wake_lowercase_accepted(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """Lowercase 'wake' is accepted.

        Technique: Boundary Value Analysis — normalisation boundary.
        """
        result = await handle_power(
            "wake", fake_wallpanel, fake_wol, wallpanel_settings
        )

        assert result == {"state": "waking"}


# =============================================================================
# handle_power — unreachable path (OFF/SLEEP only)
# =============================================================================


@pytest.mark.unit
class TestHandlePowerUnreachable:
    """Verify OFF/SLEEP when wallpanel unreachable returns None + logs warning.

    Technique: Error Guessing — WallpanelUnreachableError from hardware layer.
    """

    async def test_off_unreachable_returns_none(self, fake_wol: FakeWol) -> None:
        """OFF when wallpanel unreachable returns None (suppresses publish)."""
        # Arrange
        fake = FakeWallpanel(reachable=False)
        settings = make_wallpanel_control_settings()

        # Act
        result = await handle_power("OFF", fake, fake_wol, settings)

        # Assert
        assert result is None

    async def test_off_unreachable_logs_warning(
        self, fake_wol: FakeWol, caplog: pytest.LogCaptureFixture
    ) -> None:
        """OFF when unreachable emits a WARNING log entry."""
        # Arrange
        fake = FakeWallpanel(reachable=False)
        settings = make_wallpanel_control_settings()

        # Act
        with caplog.at_level(logging.WARNING, logger="wallpanel_control.devices.power"):
            await handle_power("OFF", fake, fake_wol, settings)

        # Assert
        assert caplog.records, "Expected at least one log record"
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    async def test_sleep_unreachable_returns_none(self, fake_wol: FakeWol) -> None:
        """SLEEP when wallpanel unreachable returns None (suppresses publish)."""
        # Arrange
        fake = FakeWallpanel(reachable=False)
        settings = make_wallpanel_control_settings()

        # Act
        result = await handle_power("SLEEP", fake, fake_wol, settings)

        # Assert
        assert result is None

    async def test_sleep_unreachable_logs_warning(
        self, fake_wol: FakeWol, caplog: pytest.LogCaptureFixture
    ) -> None:
        """SLEEP when unreachable emits a WARNING log entry."""
        # Arrange
        fake = FakeWallpanel(reachable=False)
        settings = make_wallpanel_control_settings()

        # Act
        with caplog.at_level(logging.WARNING, logger="wallpanel_control.devices.power"):
            await handle_power("SLEEP", fake, fake_wol, settings)

        # Assert
        assert caplog.records, "Expected at least one log record"
        assert any(r.levelno == logging.WARNING for r in caplog.records)


# =============================================================================
# handle_power — invalid payload
# =============================================================================


@pytest.mark.unit
class TestHandlePowerInvalidPayload:
    """Verify invalid payloads raise ValueError.

    Technique: Equivalence Partitioning — invalid input class.
    """

    @pytest.mark.parametrize(
        "bad_payload",
        [
            "ON",
            "HIBERNATE",
            "SUSPEND",
            "",
            "  ",
            "0",
            "1",
            "random",
        ],
    )
    async def test_invalid_payload_raises(
        self,
        bad_payload: str,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """Invalid payloads raise ValueError.

        Technique: Error Guessing — out-of-range and near-miss inputs.
        """
        with pytest.raises(ValueError, match="Invalid power payload"):
            await handle_power(
                bad_payload, fake_wallpanel, fake_wol, wallpanel_settings
            )
