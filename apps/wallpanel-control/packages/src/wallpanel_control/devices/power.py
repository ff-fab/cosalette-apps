"""Power command handler for wallpanel-control.

Handles inbound MQTT ``power/set`` commands, mapping OFF/SLEEP/WAKE
to the appropriate system power action.

MQTT command topic:
    wallpanel-control/power/set  ← "OFF", "SLEEP", or "WAKE" (case-insensitive)

MQTT state topic:
    wallpanel-control/power/state ← {"state": "hibernating"},
                                    {"state": "suspended"},
                                 or {"state": "waking"}

The command vocabulary uses HA-friendly ``SLEEP`` while the published state
uses the Linux power-management term ``suspended``.

For OFF and SLEEP, None is returned (suppressing publish) if the
wallpanel is unreachable at command time. WAKE is always attempted
regardless of reachability because it uses WoL, not SSH.
"""

from __future__ import annotations

import logging

import cosalette

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError, WolPort
from wallpanel_control.settings import WallpanelControlSettings

logger = logging.getLogger(__name__)

router = cosalette.Router()


@router.command("power", summary="Hibernate (OFF), suspend (SLEEP), or wake (WAKE)")
async def handle_power(
    payload: str,
    wallpanel: WallpanelPort,
    wol: WolPort,
    settings: WallpanelControlSettings,
) -> dict[str, object] | None:
    """Handle power set command.

    Parses OFF/SLEEP/WAKE (case-insensitive, whitespace stripped) from the
    raw MQTT payload and calls the appropriate action.

    Args:
        payload: Raw MQTT payload string — expected "OFF", "SLEEP", or "WAKE".
        wallpanel: Hardware adapter injected by cosalette.
        wol: Wake-on-LAN adapter injected by cosalette.
        settings: Application settings injected by cosalette.

    Returns:
        ``{"state": "hibernating"}`` for OFF.
        ``{"state": "suspended"}`` for SLEEP.
        ``{"state": "waking"}`` for WAKE.
        ``None`` when the wallpanel is unreachable (OFF/SLEEP only — suppresses publish).

    Raises:
        ValueError: When payload is not "OFF", "SLEEP", or "WAKE".
    """
    normalised = payload.strip().upper()
    if normalised not in ("OFF", "SLEEP", "WAKE"):
        msg = f"Invalid power payload: {payload!r}. Expected OFF, SLEEP, or WAKE."
        raise ValueError(msg)

    if normalised == "WAKE":
        await wol.wake(settings.wol_mac, settings.wol_broadcast)
        return {"state": "waking"}

    try:
        if normalised == "OFF":
            await wallpanel.hibernate()
            return {"state": "hibernating"}
        if normalised == "SLEEP":
            await wallpanel.suspend()
            return {"state": "suspended"}
        raise AssertionError(f"unhandled power payload: {normalised!r}")
    except WallpanelUnreachableError:
        logger.warning("Wallpanel unreachable — power command suppressed")
        return None
