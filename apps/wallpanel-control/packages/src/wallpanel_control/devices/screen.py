"""Screen command handler for wallpanel-control.

Handles inbound MQTT ``screen/set`` commands, toggling the display
on or off via D-Bus (Mutter PowerSaveMode).

MQTT command topic:
    wallpanel-control/screen/set  ← "ON" or "OFF" (case-insensitive)

MQTT state topic:
    wallpanel-control/screen/state ← {"state": "ON"} or {"state": "OFF"}

None is returned (suppressing publish) if the wallpanel is unreachable
at command time.
"""

from __future__ import annotations

import logging

import cosalette

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError

logger = logging.getLogger(__name__)

router = cosalette.Router()


@router.command("screen", summary="Turn display on or off (ON/OFF)")
async def handle_screen(
    payload: str,
    wallpanel: WallpanelPort,
) -> dict[str, object] | None:
    """Handle screen set command.

    Parses ON/OFF (case-insensitive, whitespace stripped) from the raw
    MQTT payload and calls the appropriate wallpanel method.

    Args:
        payload: Raw MQTT payload string — expected "ON" or "OFF".
        wallpanel: Hardware adapter injected by cosalette.

    Returns:
        ``{"state": "ON"}`` or ``{"state": "OFF"}`` on success.
        ``None`` when the wallpanel is unreachable (suppresses publish).

    Raises:
        ValueError: When payload is not "ON" or "OFF".
    """
    normalised = payload.strip().upper()
    if normalised not in ("ON", "OFF"):
        msg = f"Invalid screen payload: {payload!r}. Expected ON or OFF."
        raise ValueError(msg)

    try:
        if normalised == "ON":
            await wallpanel.screen_on()
        else:
            await wallpanel.screen_off()
    except WallpanelUnreachableError:
        logger.warning("Wallpanel unreachable — screen command suppressed")
        return None

    return {"state": normalised}
