"""Command payload translation for wiz2mqtt.

Pure domain logic: turns a validated :class:`~wiz2mqtt.models.BulbSetCommand`
into the keyword arguments :meth:`~wiz2mqtt.ports.WizBulbPort.set_state`
expects. No cosalette imports — testable as plain Python.
"""

from __future__ import annotations

from typing import TypedDict

from wiz2mqtt.colour import effect_name_to_scene_id, parse_hsb, rgb_to_hue_saturation
from wiz2mqtt.models import BulbSetCommand

_STATE_ON_OFF: dict[str, bool] = {"ON": True, "OFF": False}


class SetStateKwargs(TypedDict):
    """Keyword arguments for ``WizBulbPort.set_state``, typed for ``**`` splatting."""

    # mirrors WizBulbPort.set_state kwargs — keep in sync with ports.py
    state: bool | None
    """Target on/off, or ``None`` to leave it alone."""

    brightness: int | None
    """Target dimming level, or ``None``."""

    hue: float | None
    """Target hue; only applied together with ``saturation``."""

    saturation: float | None
    """Target saturation; only applied together with ``hue``."""

    color_temp_kelvin: int | None
    """Target white colour temperature, or ``None``."""

    scene: int | None
    """Target scene id, or ``None``."""

    speed: int | None
    """Target effect speed, or ``None``."""


_NO_CHANGE: SetStateKwargs = {
    "state": None,
    "brightness": None,
    "hue": None,
    "saturation": None,
    "color_temp_kelvin": None,
    "scene": None,
    "speed": None,
}


def off_kwargs() -> SetStateKwargs:
    """Return a fresh OFF write: ``state=False`` and no appearance."""
    return {**_NO_CHANGE, "state": False}


def to_set_state_kwargs(cmd: BulbSetCommand) -> SetStateKwargs:
    """Translate a validated set-command into ``WizBulbPort.set_state`` kwargs.

    Mutual exclusion between ``color``/``color_temp``/``effect``/``hsb`` is
    already enforced by ``BulbSetCommand``'s own validator — this function
    only maps units: HA's ``"ON"``/``"OFF"`` to ``bool``, RGB or openHAB's
    ``"h,s,b"`` string to canonical hue/saturation (and, for ``hsb``, its
    0-100 brightness percent to the 0-255 scale), and the HA ``effect``
    scene *name* to the numeric ``scene`` id pywizlight wants.

    A resulting brightness of ``0`` is an OFF command and nothing else: an
    openHAB Dimmer sends OFF as ``{"brightness":0}`` and a Color channel as
    an ``"h,s,0"`` triple (ADR-001 amendment 2026-09-30).

    Any other non-empty command without ``state`` means ON: the adapter
    sends it with pywizlight's ``turn_on``, which lights the bulb. Making
    that explicit here keeps the desired state, the optimistic cache and
    the power request in step with the device (ADR-008 amendment
    2026-09-30).
    """
    hue = saturation = None
    brightness = cmd.brightness
    if cmd.color is not None:
        hue, saturation = rgb_to_hue_saturation(cmd.color.r, cmd.color.g, cmd.color.b)
    elif cmd.hsb is not None:
        hue, saturation, hsb_brightness = parse_hsb(cmd.hsb)
        if brightness is None:
            brightness = hsb_brightness
    if brightness == 0:
        return off_kwargs()

    scene = effect_name_to_scene_id(cmd.effect) if cmd.effect is not None else None
    kwargs: SetStateKwargs = {
        **_NO_CHANGE,
        "brightness": brightness,
        "hue": hue,
        "saturation": saturation,
        "color_temp_kelvin": cmd.color_temp,
        "scene": scene,
        "speed": cmd.effect_speed,
    }
    if cmd.state is not None:
        kwargs["state"] = _STATE_ON_OFF[cmd.state]
    elif any(value is not None for value in kwargs.values()):
        kwargs["state"] = True
    return kwargs
