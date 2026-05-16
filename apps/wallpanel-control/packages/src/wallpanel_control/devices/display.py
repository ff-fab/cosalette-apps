"""Display command handler for wallpanel-control.

Handles inbound MQTT display/set commands and publishes display/state
after each accepted command.  No periodic polling is registered.

MQTT command topic:
    wallpanel-control/display/set
        ← {"state": "on"|"off"}
        ← {"brightness_percent": <1-100>}
        ← {"state": "on", "brightness_percent": <1-100>}

MQTT state topic:
    wallpanel-control/display/state
        ← {"available": true, "state": "on"|"off", "brightness_percent": <int>}
        ← {"available": false, "state": null, "brightness_percent": null}

When the wallpanel is unreachable the payload uses available=false and null
values.  Rejects ``{}`` or unknown-only payloads.  Combining state="off" with
brightness_percent is rejected as ambiguous.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Annotated, Literal

import cosalette
from cosalette.mqtt import Payload
from pydantic import BaseModel, ConfigDict, Field, model_validator

from wallpanel_control.ports import WallpanelPort, WallpanelUnreachableError

logger = logging.getLogger(__name__)


class DisplayCommand(BaseModel):
    """Typed payload for wallpanel-control/display/set commands."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["on", "off"] | None = None
    brightness_percent: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def _validate_command_constraints(self) -> "DisplayCommand":
        if self.state is None and self.brightness_percent is None:
            raise ValueError(
                "At least one of 'state' or 'brightness_percent' must be provided"
            )
        if self.state == "off" and self.brightness_percent is not None:
            raise ValueError("brightness_percent must not be set when state is 'off'")
        return self


class DisplayState(BaseModel):
    """Typed state for wallpanel-control/display/state."""

    available: bool
    state: Literal["on", "off"] | None
    brightness_percent: int | None = Field(ge=0, le=100)


_UNAVAILABLE = DisplayState(available=False, state=None, brightness_percent=None)


@dataclass
class _DisplayHandlerState:
    """Mutable state for the display command handler."""

    max_brightness: int | None = None


def create_display_handler_state() -> _DisplayHandlerState:
    """Build _DisplayHandlerState without exposing dataclass fields to cosalette DI."""
    return _DisplayHandlerState()


router = cosalette.Router()


async def _poll_display_state(
    wallpanel: WallpanelPort,
    state: _DisplayHandlerState,
) -> DisplayState:
    """Internal helper: read current display state from the wallpanel.

    This is an internal helper used by ``handle_display``.  It is **not**
    registered as public MQTT telemetry and does not publish on a timer.

    Args:
        wallpanel: Hardware adapter.
        state: Mutable handler state (caches max_brightness).

    Returns:
        DisplayState with current values, or unavailable state if unreachable.
    """
    if not await wallpanel.is_reachable():
        return _UNAVAILABLE

    try:
        if state.max_brightness is None:
            state.max_brightness = await wallpanel.get_max_brightness()
        if state.max_brightness == 0:
            logger.warning("Wallpanel max_brightness is 0; display unavailable")
            return _UNAVAILABLE

        raw_brightness, screen_state = await asyncio.gather(
            wallpanel.get_brightness(),
            wallpanel.get_screen_state(),
        )
    except WallpanelUnreachableError:
        logger.warning("Wallpanel became unreachable during display poll")
        return _UNAVAILABLE

    if raw_brightness is None or screen_state is None:
        return _UNAVAILABLE

    brightness_pct = round(raw_brightness / state.max_brightness * 100)
    return DisplayState(
        available=True,
        state="on" if screen_state else "off",
        brightness_percent=brightness_pct,
    )


async def _read_brightness_percent(
    wallpanel: WallpanelPort,
    state: _DisplayHandlerState,
) -> int | None:
    """Read current brightness as a percent, using cached max_brightness.

    Ensures max_brightness is lazily loaded and cached.  Returns None if
    max_brightness is 0 or raw brightness is unavailable.  Propagates
    WallpanelUnreachableError to the caller.
    """
    if state.max_brightness is None:
        state.max_brightness = await wallpanel.get_max_brightness()
    if state.max_brightness == 0:
        logger.warning("Wallpanel max_brightness is 0; display unavailable")
        return None
    raw = await wallpanel.get_brightness()
    if raw is None:
        return None
    return round(raw / state.max_brightness * 100)


async def _execute_display_command(
    cmd: DisplayCommand,
    wallpanel: WallpanelPort,
    state: _DisplayHandlerState,
) -> DisplayState:
    """Execute a display command and return resulting state.

    Args:
        cmd: Parsed and validated display command.
        wallpanel: Hardware adapter.
        state: Mutable handler state.

    Returns:
        DisplayState after executing the command, or unavailable if unreachable.
    """
    try:
        if cmd.state == "off":
            await wallpanel.screen_off()
            return await _poll_display_state(wallpanel, state)

        # From here: state is "on" or None; brightness_percent may be set.
        if cmd.state == "on":
            await wallpanel.screen_on()
            if cmd.brightness_percent is None:
                # Turn on only — read current brightness; skip redundant screen read.
                pct = await _read_brightness_percent(wallpanel, state)
                if pct is None:
                    return _UNAVAILABLE
                return DisplayState(available=True, state="on", brightness_percent=pct)

        # brightness_percent is set (state="on"+bp or bp-only).
        if cmd.state is None:
            # brightness-only: turn screen on if it is currently off
            screen_state = await wallpanel.get_screen_state()
            if screen_state is None:
                return _UNAVAILABLE
            if not screen_state:
                await wallpanel.screen_on()

        brightness_percent = cmd.brightness_percent
        if brightness_percent is None:
            raise ValueError("brightness_percent must be set for brightness commands")
        if state.max_brightness is None:
            state.max_brightness = await wallpanel.get_max_brightness()
        if state.max_brightness == 0:
            logger.warning(
                "Wallpanel max_brightness is 0; brightness command suppressed"
            )
            return _UNAVAILABLE

        raw = round(state.max_brightness * brightness_percent / 100)
        await wallpanel.set_brightness(raw)
        # Compute output brightness from raw and cached max — no read-back needed.
        brightness_pct = round(raw / state.max_brightness * 100)
        return DisplayState(
            available=True, state="on", brightness_percent=brightness_pct
        )

    except WallpanelUnreachableError:
        logger.warning("Wallpanel unreachable during display command")
        return _UNAVAILABLE


@router.command(
    "display",
    payload_model=DisplayCommand,
    state_model=DisplayState,
    init=create_display_handler_state,
    summary="Control display state and brightness",
)
async def handle_display(
    cmd: Annotated[DisplayCommand, Payload()],
    wallpanel: WallpanelPort,
    state: _DisplayHandlerState,
) -> DisplayState:
    """Handle display command.

    Args:
        cmd: Parsed display command injected by cosalette.
        wallpanel: Hardware adapter injected by cosalette.
        state: Mutable display handler state injected by cosalette.

    Returns:
        DisplayState after executing the command, or unavailable if unreachable.
    """
    return await _execute_display_command(cmd, wallpanel, state)
