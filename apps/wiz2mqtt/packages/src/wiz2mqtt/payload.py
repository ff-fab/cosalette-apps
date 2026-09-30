"""Retained state payload construction for wiz2mqtt.

Pure domain logic: turns a :class:`~wiz2mqtt.models.BulbState` into the
``{prefix}/{bulb}/state`` payload (``prefix`` defaults to ``wiz2mqtt`` when
``mqtt.topic_prefix`` is unset) — HA's ``schema: json`` light shape plus
the non-HA keys openHAB's Generic MQTT Thing consumes. No cosalette
imports — testable as plain Python.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from wiz2mqtt.colour import hue_saturation_to_rgb, is_cct_mode, scene_id_to_effect_name
from wiz2mqtt.intent import pending_write_kwargs
from wiz2mqtt.models import NULL_WIRE, POWERED_UNKNOWN

_MAX_BRIGHTNESS: int = 255
"""HA brightness scale upper bound (0-255)."""

if TYPE_CHECKING:
    from wiz2mqtt.commands import SetStateKwargs
    from wiz2mqtt.intent import AppliedCommand, PendingCommand
    from wiz2mqtt.models import BulbState, PoweredWire
    from wiz2mqtt.power import Belief


def build_state_payload(state: BulbState, powered: Belief | None) -> dict[str, object]:
    """Build the retained state payload for one bulb.

    ``state`` is always present — HA discards the whole message on
    ``KeyError`` if it's missing. Every other key is included only when
    known/applicable — see :func:`_color_fields` for the colour-mode keys.
    ``powered`` (ADR-007/ADR-001 amendment) is the exception: it is always
    present, rendered as ``true``/``false``/``null`` — ``None`` (no power
    source) and ``"unknown"`` both map to the wire ``null``.
    """
    payload: dict[str, object] = {"state": "ON" if state.state else "OFF"}
    payload.update(_color_fields(state))
    payload.update(_optional_fields(state))
    payload["powered"] = _powered_wire_value(powered)
    return payload


def _powered_wire_value(powered: Belief | None) -> PoweredWire:
    if powered == "on":
        return True
    if powered == "off":
        return False
    return POWERED_UNKNOWN


def _optional_fields(state: BulbState) -> dict[str, object]:
    """``brightness``/``effect``/``effect_speed``/``power_draw_w``, when known."""
    fields: dict[str, object] = {}
    if state.brightness is not None:
        fields["brightness"] = state.brightness
    if state.scene is not None:
        effect_name = scene_id_to_effect_name(state.scene)
        if effect_name is not None:
            fields["effect"] = effect_name
    if state.effect_speed is not None:
        fields["effect_speed"] = state.effect_speed
    if state.power_draw_w is not None and math.isfinite(state.power_draw_w):
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
            "color_temp_kelvin": True,  # HA flag: interpret color_temp as K, not mireds
        }
    if state.hue is None or state.saturation is None:
        return {}

    brightness = state.brightness if state.brightness is not None else _MAX_BRIGHTNESS
    r, g, b = hue_saturation_to_rgb(state.hue, state.saturation, brightness)
    dimming_percent = round(brightness / _MAX_BRIGHTNESS * 100)
    hue_deg = round(state.hue) % 360  # clamp: :.0f rounds 359.5 → "360"
    sat_pct = round(state.saturation)
    return {
        "color_mode": "rgb",
        "color": {"r": r, "g": g, "b": b},
        "hsb": f"{hue_deg},{sat_pct},{dimming_percent}",
    }


_WIRE_FIELD_BY_KWARG: dict[str, str] = {
    "state": "state",
    "brightness": "brightness",
    "hue": "hsb",
    "saturation": "hsb",
    "color_temp_kelvin": "color_temp",
    "scene": "effect",
    "speed": "effect_speed",
}
"""``set_state`` keyword → the ``/set`` field a consumer sends for it."""


def command_wire_fields(kwargs: SetStateKwargs) -> list[str]:
    """The ``/set`` field names a ``set_state`` write carries, in kwarg order."""
    fields = (_WIRE_FIELD_BY_KWARG[k] for k, v in kwargs.items() if v is not None)
    return list(dict.fromkeys(fields))


def readiness_fields(
    *,
    reachable: bool,
    pending: PendingCommand | None,
    ttl: float,
    last_applied: AppliedCommand | None,
) -> dict[str, object]:
    """``reachable``/``pending``/``last_applied`` — queued-command readiness.

    All three are always present; ``pending``/``last_applied`` render JSON
    ``null`` when absent (see :data:`wiz2mqtt.models.NULL_WIRE`). ``pending``
    lists the fields the return path would write: a queued OFF writes only
    ``state``, while its queued appearance waits for a later ON.
    """
    fields: dict[str, object] = {
        "reachable": reachable,
        "pending": NULL_WIRE,
        "last_applied": NULL_WIRE,
    }
    if pending is not None:
        fields["pending"] = {
            "fields": command_wire_fields(pending_write_kwargs(pending.kwargs)),
            "queued_at": round(pending.queued_at),
            "expires_at": round(pending.queued_at + ttl),
        }
    if last_applied is not None:
        fields["last_applied"] = {
            "at": round(last_applied.at),
            "fields": command_wire_fields(last_applied.kwargs),
            "attempts": last_applied.attempts,
            "confirmed": last_applied.confirmed,
        }
    return fields
