"""Brightness command handler for wallpanel-control.

Handles inbound MQTT ``brightness/set`` commands, mapping the 0-100%
percentage payload to a raw sysfs backlight value and issuing the
appropriate SSH commands to the wallpanel.

MQTT command topic:
    wallpanel-control/brightness/set  ← integer string 0-100

MQTT state topic:
    wallpanel-control/brightness/state ← {"brightness": <int 0-100>}

When brightness is 0 the screen is turned off. When brightness is > 0
and the screen is currently off, the screen is turned on first before
setting the raw brightness value.

None is returned (suppressing publish) if the wallpanel is unreachable
at command time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import cosalette

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError

logger = logging.getLogger(__name__)


@dataclass
class BrightnessState:
    """Mutable state for the brightness command handler.

    Holds the max_brightness value lazily read on first non-zero command
    (used to scale percentages to raw sysfs values) and the last
    successfully applied percentage so callers can inspect current intent.
    """

    max_brightness: int | None = None
    last_known_brightness: int | None = field(default=None)


def create_brightness_state() -> BrightnessState:
    """Synchronous zero-arg factory for BrightnessState.

    max_brightness is lazily initialized on the first non-zero brightness
    command by reading from the wallpanel at command time.

    Returns:
        A fresh BrightnessState with max_brightness=None.
    """
    return BrightnessState()


router = cosalette.Router()


@router.command(
    "brightness",
    init=create_brightness_state,
    summary="Set display brightness (0-100%)",
)
async def handle_brightness(
    payload: str,
    wallpanel: WallpanelPort,
    state: BrightnessState,
) -> dict[str, object] | None:
    """Handle brightness set command.

    Parses an integer percentage (0-100) from the raw MQTT payload, maps
    it to a raw sysfs value, and applies it via the wallpanel port.

    A value of 0 turns the screen off; values 1-100 turn the screen on
    (if needed) and set brightness proportionally.

    Args:
        payload: Raw MQTT payload string — expected integer 0-100.
        wallpanel: Hardware adapter (injected by cosalette DI).
        state: Mutable brightness state (injected by cosalette DI).

    Returns:
        ``{"brightness": <percentage>}`` on success, or None if the
        wallpanel is unreachable (suppresses MQTT publish).

    Raises:
        ValueError: If payload is not a valid integer or is outside 0-100.
    """
    brightness = int(payload.strip())
    if not 0 <= brightness <= 100:
        raise ValueError(f"brightness must be 0-100, got {brightness}")

    try:
        if brightness == 0:
            await wallpanel.screen_off()
            state.last_known_brightness = 0
            return {"brightness": 0}

        if state.max_brightness is None:
            state.max_brightness = await wallpanel.get_max_brightness()

        screen_state = await wallpanel.get_screen_state()
        if screen_state is None:
            logger.warning(
                "Wallpanel unreachable (get_screen_state returned None); "
                "skipping brightness command"
            )
            return None

        if not screen_state:
            await wallpanel.screen_on()

        raw = round(state.max_brightness * brightness / 100)
        await wallpanel.set_brightness(raw)
        state.last_known_brightness = brightness
        return {"brightness": brightness}

    except WallpanelUnreachableError:
        logger.warning(
            "Wallpanel unreachable (WallpanelUnreachableError); skipping brightness command"
        )
        return None
