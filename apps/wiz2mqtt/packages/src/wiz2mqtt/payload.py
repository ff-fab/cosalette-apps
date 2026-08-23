"""Retained state payload construction for wiz2mqtt (cap-10u.13).

Pure domain logic: turns a :class:`~wiz2mqtt.models.BulbState` into the
``wiz2mqtt/{bulb}/state`` payload — HA's ``schema: json`` light shape plus
the non-HA keys openHAB's Generic MQTT Thing consumes. No cosalette
imports — testable as plain Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wiz2mqtt.colour import hue_saturation_to_rgb, is_cct_mode

if TYPE_CHECKING:
    from wiz2mqtt.models import BulbState


def build_state_payload(state: BulbState) -> dict[str, object]:
    """Build the retained state payload for one bulb.

    ``state`` is always present — HA discards the whole message on
    ``KeyError`` if it's missing. Every other key is included only when
    known/applicable — see :func:`_color_fields` for the colour-mode keys.
    """
    payload: dict[str, object] = {"state": "ON" if state.state else "OFF"}
    payload.update(_color_fields(state))
    payload.update(_optional_fields(state))
    return payload


def _optional_fields(state: BulbState) -> dict[str, object]:
    """``brightness``/``effect``/``effect_speed``/``power_draw_w``, when known."""
    fields: dict[str, object] = {}
    if state.brightness is not None:
        fields["brightness"] = state.brightness
    if state.scene is not None:
        fields["effect"] = state.scene
    if state.effect_speed is not None:
        fields["effect_speed"] = state.effect_speed
    if state.power_draw_w is not None:
        fields["power_draw_w"] = round(state.power_draw_w, 1)
    return fields


def _color_fields(state: BulbState) -> dict[str, object]:
    """``color_mode``/``color``/``color_temp``/``hsb``, gated on the bulb's mode.

    HA reads ``color``/``color_temp`` only inside a branch gated on
    ``color_mode`` (see :func:`wiz2mqtt.colour.is_cct_mode`), so these keys
    are omitted entirely rather than published as null. ``hsb`` uses
    openHAB's Color channel format (``"h,s,b"``, brightness as a 0-100
    dimming percent, not the 0-255 HA ``brightness`` key).
    """
    if is_cct_mode(state.color_temp_kelvin):
        return {
            "color_mode": "color_temp",
            "color_temp": state.color_temp_kelvin,
            "color_temp_kelvin": True,
        }
    if state.hue is None or state.saturation is None:
        return {}

    brightness = state.brightness if state.brightness is not None else 255
    r, g, b = hue_saturation_to_rgb(state.hue, state.saturation, brightness)
    dimming_percent = round(brightness / 255 * 100)
    return {
        "color_mode": "rgb",
        "color": {"r": r, "g": g, "b": b},
        "hsb": f"{state.hue:.0f},{state.saturation:.0f},{dimming_percent}",
    }
