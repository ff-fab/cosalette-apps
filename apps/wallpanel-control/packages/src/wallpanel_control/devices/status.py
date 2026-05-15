"""Status telemetry handler for wallpanel-control.

Polls wallpanel availability, brightness percentage, and screen state on a
configurable interval and publishes only on change.

MQTT state topic:
    wallpanel-control/status/state ← {"available": bool, "brightness": int|null,
                                       "screen": "ON"|"OFF"|null}

When the wallpanel is unreachable the payload contains ``available: false``
and null values for brightness and screen.  On the first successful poll
the handler lazy-initialises ``state.max_brightness`` by reading the hardware
maximum — subsequent polls reuse the cached value.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import cosalette

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError
from wallpanel_control.settings import WallpanelControlSettings

logger = logging.getLogger(__name__)


@dataclass
class StatusState:
    """Mutable state for the status telemetry handler.

    Holds the lazily-initialised max_brightness value read from hardware on
    the first successful poll so subsequent polls avoid the extra SSH round-trip.
    """

    max_brightness: int | None = None


_UNAVAILABLE: dict[str, object] = {
    "available": False,
    "brightness": None,
    "screen": None,
}


def create_status_state() -> StatusState:
    """Build StatusState without exposing dataclass fields to cosalette DI."""
    return StatusState()


def _status_interval(s: cosalette.Settings) -> float:
    """Deferred interval — resolved after settings are parsed.

    Args:
        s: Application settings injected by cosalette.

    Returns:
        Poll interval in seconds from WallpanelControlSettings.

    Raises:
        TypeError: When *s* is not a WallpanelControlSettings instance.
    """
    if not isinstance(s, WallpanelControlSettings):
        msg = f"Expected WallpanelControlSettings, got {type(s).__name__}"
        raise TypeError(msg)
    return s.poll_interval


router = cosalette.Router()


@router.telemetry(
    "status",
    interval=_status_interval,
    publish=cosalette.OnChange(),
    triggerable=True,
    init=create_status_state,
    summary="Read wallpanel availability, brightness percentage, and screen state",
)
async def poll_status(
    wallpanel: WallpanelPort,
    state: StatusState,
    trigger: cosalette.TriggerPayload,
) -> dict[str, object]:
    """Poll wallpanel status and return normalised state dict.

    Args:
        wallpanel: Hardware adapter injected by cosalette.
        state: Mutable handler state injected by cosalette.
        trigger: Trigger context — populated on on-demand MQTT triggers.

    Returns:
        ``{"available": True, "brightness": <pct>, "screen": "ON"|"OFF"}``
        when reachable, or ``{"available": False, "brightness": None, "screen": None}``
        when the wallpanel cannot be reached.
    """
    if trigger.is_triggered:
        logger.debug("Status poll triggered on demand")

    # Fast availability signal for the common asleep case; reads below still
    # handle the TOCTOU window where the panel goes offline after this check.
    if not await wallpanel.is_reachable():
        return _UNAVAILABLE

    try:
        if state.max_brightness is None:
            state.max_brightness = await wallpanel.get_max_brightness()
        if state.max_brightness == 0:
            logger.warning("Wallpanel max_brightness is 0; status unavailable")
            return _UNAVAILABLE
        raw_brightness, screen_state = await asyncio.gather(
            wallpanel.get_brightness(),
            wallpanel.get_screen_state(),
        )
    except WallpanelUnreachableError:
        logger.warning("Wallpanel became unreachable during status poll")
        return _UNAVAILABLE

    if raw_brightness is None or screen_state is None:
        return _UNAVAILABLE

    brightness_pct = round(raw_brightness / state.max_brightness * 100)
    return {
        "available": True,
        "brightness": brightness_pct,
        "screen": "ON" if screen_state else "OFF",
    }
