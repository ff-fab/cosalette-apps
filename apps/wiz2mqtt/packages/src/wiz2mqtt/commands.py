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
    brightness: int | None
    hue: float | None
    saturation: float | None
    color_temp_kelvin: int | None
    scene: int | None
    speed: int | None


def to_set_state_kwargs(cmd: BulbSetCommand) -> SetStateKwargs:
    """Translate a validated set-command into ``WizBulbPort.set_state`` kwargs.

    Mutual exclusion between ``color``/``color_temp``/``effect``/``hsb`` is
    already enforced by ``BulbSetCommand``'s own validator — this function
    only maps units: HA's ``"ON"``/``"OFF"`` to ``bool``, RGB or openHAB's
    ``"h,s,b"`` string to canonical hue/saturation (and, for ``hsb``, its
    0-100 brightness percent to the 0-255 scale), and the HA ``effect``
    scene *name* to the numeric ``scene`` id pywizlight wants.
    """
    hue = saturation = None
    brightness = cmd.brightness
    if cmd.color is not None:
        hue, saturation = rgb_to_hue_saturation(cmd.color.r, cmd.color.g, cmd.color.b)
    elif cmd.hsb is not None:
        hue, saturation, hsb_brightness = parse_hsb(cmd.hsb)
        if brightness is None:
            brightness = hsb_brightness

    scene = effect_name_to_scene_id(cmd.effect) if cmd.effect is not None else None
    return {
        "state": _STATE_ON_OFF.get(cmd.state),
        "brightness": brightness,
        "hue": hue,
        "saturation": saturation,
        "color_temp_kelvin": cmd.color_temp,
        "scene": scene,
        "speed": cmd.effect_speed,
    }
