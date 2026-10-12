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

from typing import Literal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.devices.restore import LastAnswers
from wallpanel_control.devices.system import (
    PANEL_PROBE,
    SystemActionCommand,
    SystemActionState,
    handle_system_action,
    router,
)
from wallpanel_control.settings import WallpanelControlSettings


@pytest.fixture
def notify() -> MagicMock:
    """Stand-in for the EntityNotifier that wakes the panel probe."""
    return MagicMock()


@pytest.fixture
def ctx() -> MagicMock:
    """Stand-in for the device context clock used to timestamp acceptance."""
    context = MagicMock()
    context.clock.now.return_value = 123.0
    return context


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
        assert s.model_dump() == {"accepted": True, "action": "wake", "observed": None}

    def test_accepted_false_serialises(self) -> None:
        """accepted=False with action serialises correctly."""
        s = SystemActionState(accepted=False, action="suspend")
        assert s.model_dump() == {
            "accepted": False,
            "action": "suspend",
            "observed": None,
        }


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
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """wake action calls wol.wake() with mac and broadcast from settings."""
        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="wake"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
        )

        assert fake_wol.calls == [
            (wallpanel_settings.wol_mac, wallpanel_settings.wol_broadcast)
        ]
        assert result.accepted is True
        assert result.action == "wake"

    async def test_wake_returns_accepted_true(
        self,
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """wake always returns accepted=True regardless of wallpanel state."""
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="wake"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
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
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """suspend action calls wallpanel.suspend()."""
        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="suspend"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
        )

        assert fake_wallpanel.power_state == "suspended"
        assert result.accepted is True
        assert result.action == "suspend"

    async def test_suspend_unreachable_returns_accepted_false(
        self,
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """suspend when unreachable returns accepted=False.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="suspend"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
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
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """hibernate action calls wallpanel.hibernate()."""
        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="hibernate"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
        )

        assert fake_wallpanel.power_state == "hibernating"
        assert result.accepted is True
        assert result.action == "hibernate"

    async def test_hibernate_unreachable_returns_accepted_false(
        self,
        ctx: MagicMock,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
    ) -> None:
        """hibernate when unreachable returns accepted=False.

        Technique: Branch/Condition Coverage — unreachable path.
        """
        fake_wallpanel.set_reachable(False)

        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="hibernate"),
            fake_wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
        )

        assert result.accepted is False
        assert result.action == "hibernate"


# =============================================================================
# handle_system_action — sleep already pending
# =============================================================================


@pytest.mark.unit
class TestHandleSystemActionSleepPending:
    """Verify a sleep request during a pending sleep is acknowledged, not an error.

    Technique: Error Guessing — repeated suspend while gnome-shell's delay
    inhibitor holds the first one (adopter report F8).
    """

    @pytest.mark.parametrize("action", ["suspend", "hibernate"])
    async def test_sleep_pending_returns_accepted_true(
        self,
        action: Literal["suspend", "hibernate"],
        fake_wol: FakeWol,
        wallpanel_settings: WallpanelControlSettings,
        notify: MagicMock,
        ctx: MagicMock,
    ) -> None:
        """A repeat during a pending suspend answers accepted=True, raising nothing."""
        # Arrange
        wallpanel = FakeWallpanel(sleep_delayed=True)
        await getattr(wallpanel, action)()

        # Act
        result = await handle_system_action(
            ctx,
            SystemActionCommand(action=action),
            wallpanel,
            fake_wol,
            wallpanel_settings,
            LastAnswers(),
            notify,
        )

        # Assert
        assert result == SystemActionState(
            accepted=True, action=action, observed="pending"
        )
        assert wallpanel.power_state == (
            "suspended" if action == "suspend" else "hibernating"
        )


# =============================================================================
# router registration
# =============================================================================


@pytest.mark.unit
class TestRouterRegistration:
    """Verify the router registers 'action' with system prefix.

    Technique: Specification-based — public API contract.
    """

    def test_action_in_registered_names(self) -> None:
        """Router has a command registered as 'action' (becomes system/action
        after prefix)."""
        assert "action" in router.registered_names

    def test_no_telemetry_or_devices_registered(self) -> None:
        """Router exposes no telemetry or device registrations — commands only.

        Technique: Structural — documents the expected empty collections
        now that router.telemetry_registrations and router.devices are public.
        """
        assert list(router.telemetry_registrations) == []
        assert list(router.devices) == []

    def test_action_command_payload_model(self) -> None:
        """payload_model is SystemActionCommand.

        Technique: Structural — payload_model drives AsyncAPI manifest schema.
        """
        reg = next((r for r in router.commands if r.name == "action"), None)
        assert reg is not None, "'action' not registered on router"
        assert reg.payload_model is SystemActionCommand

    def test_action_command_state_model(self) -> None:
        """state_model is SystemActionState.

        Technique: Structural — state_model drives AsyncAPI manifest schema.
        """
        reg = next((r for r in router.commands if r.name == "action"), None)
        assert reg is not None, "'action' not registered on router"
        assert reg.state_model is SystemActionState


# =============================================================================
# handle_system_action — observed outcome (app ADR-001)
# =============================================================================


@pytest.mark.unit
class TestHandleSystemActionObserved:
    """Verify the acknowledgement starts a probe confirmation when it should.

    Technique: Decision Table — accepted x probe enabled decides observed and
    whether the probe is woken.
    """

    @pytest.mark.parametrize(
        ("reachable", "probe_enabled", "observed"),
        [
            (True, True, "pending"),
            (False, True, None),
            (True, False, None),
        ],
    )
    async def test_observed_and_probe_wake(
        self,
        ctx: MagicMock,
        fake_wol: FakeWol,
        notify: MagicMock,
        reachable: bool,
        probe_enabled: bool,
        observed: str | None,
    ) -> None:
        """Only an accepted action with the probe enabled is pending and wakes it."""
        # Arrange
        wallpanel = FakeWallpanel(reachable=reachable)
        settings = make_wallpanel_control_settings(probe_enabled=probe_enabled)
        answers = LastAnswers()

        # Act
        result = await handle_system_action(
            ctx,
            SystemActionCommand(action="suspend"),
            wallpanel,
            fake_wol,
            settings,
            answers,
            notify,
        )

        # Assert
        assert result.observed == observed
        assert answers.current("system/action/state") == result.model_dump(mode="json")
        if observed is None:
            notify.assert_not_called()
        else:
            notify.assert_called_once_with(PANEL_PROBE)
            assert answers.accepted_at("system/action/state") == 123.0
