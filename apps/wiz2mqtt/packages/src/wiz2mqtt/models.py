"""Domain models for WiZ bulb capabilities and state.

Kept independent of ``pywizlight`` types so the ``WizBulbPort`` protocol
never leaks the SDK's shapes across the hexagonal boundary.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class BulbCapabilities:
    """A bulb's auto-detected capabilities (never declared in config).

    Populated from ``pywizlight``'s ``get_bulbtype()`` at first contact.
    """

    bulb_class: str
    color: bool
    color_tmp: bool
    effect: bool
    brightness: bool
    kelvin_min: int | None
    kelvin_max: int | None


@dataclass(frozen=True)
class BulbState:
    """Canonical bulb state: (hue, saturation, dimming), never RGB.

    ``hue``/``saturation`` are derived from ``pywizlight``'s RGB readback,
    since its state accessors expose no HSB getter directly. Uses
    pywizlight's own convention: hue in ``0..360``, saturation in
    ``0..100`` (see :mod:`wiz2mqtt.colour`).
    """

    state: bool | None
    brightness: int | None
    hue: float | None
    saturation: float | None
    color_temp_kelvin: int | None
    scene: int | None

    def replace_non_none(self, **updates: object) -> BulbState:
        """Return a copy with only the non-``None`` *updates* applied.

        Used for partial-update semantics: merging a command's given
        fields onto cached/default state while leaving unset fields alone.
        """
        filtered = {k: v for k, v in updates.items() if v is not None}
        return dataclasses.replace(self, **filtered)
