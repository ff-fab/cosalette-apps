"""System action command handler for wallpanel-control.

Handles inbound MQTT system/action/set commands, mapping wake/suspend/hibernate
actions to the appropriate system power operation.

MQTT command topic:
    wallpanel-control/system/action/set
        ← {"action": "wake"|"suspend"|"hibernate"}

MQTT state topic:
    wallpanel-control/system/action/state
        ← {"accepted": true, "action": "wake"|"suspend"|"hibernate"}
        ← {"accepted": false, "action": "suspend"|"hibernate"}

wake always succeeds (uses WoL — no SSH required).
suspend and hibernate require SSH reachability; returns accepted=false when
the wallpanel is unreachable.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

import cosalette
from cosalette.mqtt import Payload
from pydantic import BaseModel, ConfigDict

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError, WolPort
from wallpanel_control.settings import WallpanelControlSettings

logger = logging.getLogger(__name__)


class SystemActionCommand(BaseModel):
    """Typed payload for wallpanel-control/system/action/set commands."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["wake", "suspend", "hibernate"]


class SystemActionState(BaseModel):
    """Typed state for wallpanel-control/system/action/state."""

    accepted: bool
    action: Literal["wake", "suspend", "hibernate"]


router = cosalette.Router(prefix="system")


@router.command(
    "action",
    summary="System power action: wake (WoL), suspend, or hibernate",
    payload_model=SystemActionCommand,
    state_model=SystemActionState,
)
async def handle_system_action(
    cmd: Annotated[SystemActionCommand, Payload()],
    wallpanel: WallpanelPort,
    wol: WolPort,
    settings: WallpanelControlSettings,
) -> SystemActionState:
    """Handle system action command.

    Args:
        cmd: Parsed system action command.
        wallpanel: Hardware adapter injected by cosalette.
        wol: Wake-on-LAN adapter injected by cosalette.
        settings: Application settings injected by cosalette.

    Returns:
        SystemActionState with accepted=True on success, accepted=False when
        the wallpanel is unreachable (suspend/hibernate only).
    """
    if cmd.action == "wake":
        await wol.wake(settings.wol_mac, settings.wol_broadcast)
        return SystemActionState(accepted=True, action="wake")

    try:
        if cmd.action == "suspend":
            await wallpanel.suspend()
        else:
            await wallpanel.hibernate()
        return SystemActionState(accepted=True, action=cmd.action)
    except WallpanelUnreachableError:
        logger.warning("Wallpanel unreachable — system %s suppressed", cmd.action)
        return SystemActionState(accepted=False, action=cmd.action)
