"""Unit tests for devices/system.py — system action command handler.

Test Techniques Used:
- Equivalence Partitioning: wake, suspend, hibernate as distinct valid action
  classes; invalid action strings as a separate class.
- Branch/Condition Coverage: wake path (WoL), suspend path, hibernate path,
  unreachable path for suspend and hibernate, accepted=false path.
- Error Guessing: extra fields (extra='forbid'), missing action, invalid action.
- Specification-based Testing: router registration, return shapes, WoL call
  forwarding for wake, typed ack with accepted=false on unreachable.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.devices.system import (
    SystemActionCommand,
    SystemActionState,
    handle_system_action,
    router,
)
from wallpanel_control.settings import WallpanelControlSettings


# =============================================================================
# SystemActionCommand — validation
# =============================================================================


@pytest.mark.unit
class TestSystemActionCommandValidation:
    """Verify SystemActionCommand Pydantic validation rules.

    Technique: Equivalence Partitioning + Error Guessing.
    """

    def test_wake_is_valid(self) -> None:
        """action='wake' is a valid command."""
        cmd = SystemActionCommand(action="wake")
        assert cmd.action == "wake"

    def test_suspend_is_valid(self) -> None:
        """action='suspend' is a valid command."""
        cmd = SystemActionCommand(action="suspend")
        assert cmd.action == "suspend"

    def test_hibernate_is_valid(self) -> None:
        """action='hibernate' is a valid command."""
        cmd = SystemActionCommand(action="hibernate")
        assert cmd.action == "hibernate"

    def test_invalid_action_raises_validation_error(self) -> None:
        """Unknown action value raises ValidationError.

        Technique: Equivalence Partitioning — invalid action class.
        """
        with pytest.raises(ValidationError):
            SystemActionCommand(action="sleep")  # type: ignore[arg-type]

    def test_uppercase_wake_raises_validation_error(self) -> None:
        """Uppercase 'WAKE' is rejected — Literal requires exact case.

        Technique: Error Guessing — old API used uppercase.
        """
        with pytest.raises(ValidationError):
            SystemActionCommand(action="WAKE")  # type: ignore[arg-type]

    def test_extra_field_raises_validation_error(self) -> None:
        """Unknown extra fields are rejected (extra='forbid').

        Technique: Specification-based — strict payload contract.
        """
        with pytest.raises(ValidationError):
            SystemActionCommand.model_validate({"action": "wake", "unknown": "value"})

    def test_missing_action_raises_validation_error(self) -> None:
        """Missing action field raises ValidationError.

        Technique: Error Guessing — omitted required field.
        """
        with pytest.raises(ValidationError):
            SystemActionCommand.model_validate({})


# =============================================================================
# SystemActionState — model
# =============================================================================


@pytest.mark.unit
class TestSystemActionState:
    """Verify SystemActionState model.

    Technique: Specification-based — output contract.
    """

    def test_accepted_true_serialises(self) -> None:
        """accepted=True with action serialises correctly."""
        s = SystemActionState(accepted=True, action="wake")
        assert s.model_dump() == {"accepted": True, "action": "wake"}

    def test_accepted_false_serialises(self) -> None:
        """accepted=False with action serialises correctly."""
        s = SystemActionState(accepted=False, action="suspend")
        assert s.model_dump() == {"accepted": False, "action": "suspend"}


# =============================================================================
# handle_system_action — wake path
# =============================================================================


@pytest.mark.unit
class TestHandleSystemActionWake:
    """Verify wake action sends WoL packet.

    Technique: Equivalence Partitioning — wake input class.
    """

    async def test_wake_calls_wol(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """wake action calls wol.wake() with mac and broadcast from settings."""
        result = await handle_system_action(
            SystemActionCommand(action="wake"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert fake_wol.calls == [
            (wallpanel_settings.wol_mac, wallpanel_settings.wol_broadcast)
        ]
        assert result.accepted is True
        assert result.action == "wake"

    async def test_wake_returns_accepted_true(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """wake always returns accepted=True regardless of wallpanel state."""
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            SystemActionCommand(action="wake"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert result.accepted is True


# =============================================================================
# handle_system_action — suspend path
# =============================================================================


@pytest.mark.unit
class TestHandleSystemActionSuspend:
    """Verify suspend action calls wallpanel.suspend().

    Technique: Equivalence Partitioning — suspend input class.
    """

    async def test_suspend_calls_suspend(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """suspend action calls wallpanel.suspend()."""
        result = await handle_system_action(
            SystemActionCommand(action="suspend"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert fake_wallpanel.power_state == "suspended"
        assert result.accepted is True
        assert result.action == "suspend"

    async def test_suspend_unreachable_returns_accepted_false(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """suspend when unreachable returns accepted=False.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            SystemActionCommand(action="suspend"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert result.accepted is False
        assert result.action == "suspend"


# =============================================================================
# handle_system_action — hibernate path
# =============================================================================


@pytest.mark.unit
class TestHandleSystemActionHibernate:
    """Verify hibernate action calls wallpanel.hibernate().

    Technique: Equivalence Partitioning — hibernate input class.
    """

    async def test_hibernate_calls_hibernate(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """hibernate action calls wallpanel.hibernate()."""
        result = await handle_system_action(
            SystemActionCommand(action="hibernate"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert fake_wallpanel.power_state == "hibernating"
        assert result.accepted is True
        assert result.action == "hibernate"

    async def test_hibernate_unreachable_returns_accepted_false(
        self,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
    ) -> None:
        """hibernate when unreachable returns accepted=False.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            SystemActionCommand(action="hibernate"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
        )

        assert result.accepted is False
        assert result.action == "hibernate"


# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router registers 'action' with system prefix.

    Technique: Specification-based — public API contract.
    """

    def test_action_in_registered_names(self) -> None:
        """Router has a command registered as 'action' (becomes system/action after prefix)."""
        assert "action" in router.registered_names
