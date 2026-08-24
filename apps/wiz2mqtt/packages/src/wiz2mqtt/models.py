"""Domain models for WiZ bulb capabilities and state.

Kept independent of ``pywizlight`` types so the ``WizBulbPort`` protocol
never leaks the SDK's shapes across the hexagonal boundary.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    effect_speed: int | None = None
    """Colour-changing effect speed, from pywizlight's ``get_speed()``."""

    power_draw_w: float | None = None
    """Live power draw in watts, from pywizlight's ``get_power()``."""

    def replace_non_none(self, **updates: object) -> BulbState:
        """Return a copy with only the non-``None`` *updates* applied.

        Used for partial-update semantics: merging a command's given
        fields onto cached/default state while leaving unset fields alone.
        """
        filtered = {k: v for k, v in updates.items() if v is not None}
        return dataclasses.replace(self, **filtered)


class BulbColor(BaseModel):
    """RGB triple as HA's JSON light schema conveys it (0-255 per channel)."""

    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)


class BulbSetCommand(BaseModel):
    """Inbound ``.../set`` payload — HA's JSON light schema, every field optional.

    HA sends multi-field payloads (``{"state": "ON", "brightness": 128}``);
    openHAB's ``formatBeforePublish`` sends single-field payloads. Every
    field defaults to ``None`` so both are valid partial updates.

    ``color``, ``color_temp`` and ``effect`` are mutually exclusive.  This
    cannot be enforced downstream: ``pywizlight`` never raises on
    conflicting kwargs — rgb+scene silently merges both onto one pilot
    (firmware race), and rgb+colortemp silently drops temp by fixed
    source-order priority regardless of kwarg order. Validating here
    rejects the whole payload instead of picking a winner.
    """

    model_config = ConfigDict(extra="ignore")

    state: Literal["ON", "OFF"] | None = None
    brightness: int | None = Field(default=None, ge=1, le=255)
    color: BulbColor | None = None
    color_temp: int | None = Field(default=None, gt=0, le=10000)
    effect: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def _at_most_one_color_mode(self) -> BulbSetCommand:
        if not any((self.color, self.color_temp, self.effect)):
            return self
        given = sum(f is not None for f in (self.color, self.color_temp, self.effect))
        if given > 1:
            raise ValueError("color, color_temp and effect are mutually exclusive")
        return self
