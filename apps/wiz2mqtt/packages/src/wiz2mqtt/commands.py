"""Command payload translation for wiz2mqtt.

Pure domain logic: turns a validated :class:`~wiz2mqtt.models.BulbSetCommand`
into the keyword arguments :meth:`~wiz2mqtt.ports.WizBulbPort.set_state`
expects. No cosalette imports — testable as plain Python.
"""

from __future__ import annotations

from typing import TypedDict

from wiz2mqtt.colour import rgb_to_hue_saturation
from wiz2mqtt.models import BulbSetCommand

_STATE_ON_OFF: dict[str, bool] = {"ON": True, "OFF": False}


class SetStateKwargs(TypedDict):
    """Keyword arguments for ``WizBulbPort.set_state``, typed for ``**`` splatting."""

    state: bool | None
    brightness: int | None
    hue: float | None
    saturation: float | None
    color_temp_kelvin: int | None
    scene: int | None


def to_set_state_kwargs(cmd: BulbSetCommand) -> SetStateKwargs:
    """Translate a validated set-command into ``WizBulbPort.set_state`` kwargs.

    Mutual exclusion between ``color``/``color_temp``/``effect`` is already
    enforced by ``BulbSetCommand``'s own validator — this function only
    maps units: HA's ``"ON"``/``"OFF"`` to ``bool``, RGB to canonical
    hue/saturation.
    """
    hue = saturation = None
    if cmd.color is not None:
        hue, saturation = rgb_to_hue_saturation(cmd.color.r, cmd.color.g, cmd.color.b)

    return {
        "state": _STATE_ON_OFF.get(cmd.state) if cmd.state is not None else None,
        "brightness": cmd.brightness,
        "hue": hue,
        "saturation": saturation,
        "color_temp_kelvin": cmd.color_temp,
        "scene": cmd.effect,
    }
