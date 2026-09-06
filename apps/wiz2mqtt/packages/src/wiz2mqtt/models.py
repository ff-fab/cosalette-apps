"""Domain models for WiZ bulb capabilities and state.

Kept independent of ``pywizlight`` types so the ``WizBulbPort`` protocol
never leaks the SDK's shapes across the hexagonal boundary.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Annotated, Literal

from cosalette.schema import consumer, ha_entities, ha_entity, merge, openhab
from pydantic import BaseModel, ConfigDict, Field, model_validator

_KELVIN_MIN = 2200
_KELVIN_MAX = 6500
"""Static wire-format Kelvin bounds advertised to Home Assistant.

Per-bulb capability filtering of the discovery metadata is deliberately
deferred (see ``docs/adr/`` — TOML inventory boundary ADR, and cap-10u.14's
follow-up).  Runtime auto-detection still governs which commands the adapter
actually forwards to a given bulb; only the *advertised* range is static.
"""

_EFFECT_SPEED_MIN = 10
_EFFECT_SPEED_MAX = 200
"""pywizlight's accepted ``speed`` range (``_validate_speed_or_raise``)."""

WIZ_EFFECT_LIST: tuple[str, ...] = (
    "Alarm",
    "Bedtime",
    "Candlelight",
    "Christmas",
    "Club",
    "Cool white",
    "Cozy",
    "Daylight",
    "Deep dive",
    "Dim-to-warm",
    "Diwali",
    "Fall",
    "Fireplace",
    "Focus",
    "Forest",
    "Golden white",
    "Halloween",
    "Jungle",
    "Mojito",
    "Night light",
    "Ocean",
    "Party",
    "Pastel colors",
    "Plantgrowth",
    "Pulse",
    "Relax",
    "Rhythm",
    "Romance",
    "Snowy sky",
    "Spring",
    "Steampunk",
    "Summer",
    "Sunset",
    "True colors",
    "TV time",
    "Wake-up",
    "Warm white",
    "White",
)
"""Every named WiZ scene (``pywizlight.scenes.SCENES``), minus the ten
firmware ``Custom Mode N`` slots — advertised statically as the HA
``light`` ``effect_list`` (see :data:`_KELVIN_MIN`).
"""

# One HA ``light`` entity spans the whole JSON body; the discovery generator
# merges the telemetry ``/state`` (send) and command ``/set`` (receive)
# channels — which share these specs — into a single entity carrying both a
# ``state_topic`` and a ``command_topic`` (cosalette ADR-057).
_HA_LIGHT_ENTITY = ha_entity(
    component="light",
    extra={
        "schema": "json",
        "brightness": True,
        "supported_color_modes": ["color_temp", "rgb"],
        "effect": True,
        "effect_list": list(WIZ_EFFECT_LIST),
        "min_kelvin": _KELVIN_MIN,
        "max_kelvin": _KELVIN_MAX,
    },
)
"""Composite HA ``light`` (``schema: json``) — declared on both payload models."""

_HA_EFFECT_SPEED_ENTITY = ha_entity(
    component="number",
    name="Effect speed",
    extra={
        "value_template": "{{ value_json.effect_speed }}",
        "command_template": '{"effect_speed": {{ value }}}',
        "min": _EFFECT_SPEED_MIN,
        "max": _EFFECT_SPEED_MAX,
        "step": 1,
        "icon": "mdi:speedometer",
        "mode": "slider",
    },
)
"""Composite HA ``number`` for colour-cycling effect speed (state + command)."""

_HA_POWER_SENSOR_ENTITY = ha_entity(
    component="sensor",
    name="Power",
    extra={
        "device_class": "power",
        "unit_of_measurement": "W",
        "state_class": "measurement",
        "value_template": "{{ value_json.power_draw_w }}",
    },
)
"""Composite HA ``sensor`` for live power draw — state-only, so state model only."""

# openHAB Generic MQTT Thing channels are generated per-field from ``consumer()``
# + ``openhab()`` annotations (the offline ``cosalette schema openhab`` path —
# openHAB has no runtime discovery).  ON/OFF is published as an explicit JSON
# object because openHAB emits a channel's ``on``/``off`` value *verbatim*,
# bypassing ``formatBeforePublish``.
_OPENHAB_ON = '{"state": "ON"}'
_OPENHAB_OFF = '{"state": "OFF"}'


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


class BulbStateModel(BaseModel):
    """Retained ``wiz2mqtt/{bulb}/state`` payload shape (cap-10u.14).

    Declared as ``state_model=`` on the ``bulb_entity`` telemetry
    (:mod:`wiz2mqtt.main`) so every published payload is validated and
    normalised against this shape (cosalette 0.9.0).  Every field is
    optional: :func:`wiz2mqtt.payload.build_state_payload` includes a key
    only when it is known/applicable, and ``state_model`` validation dumps
    with ``exclude_none=True``, so that conditional-key wire shape is
    preserved exactly.

    The model carries the composite HA ``light``/``sensor``/``number``
    discovery entities (``ha_entities`` on ``model_config``); ``app.discovery()``
    and the offline ``cosalette schema ha-discovery`` path emit them per
    configured bulb (cap-10u.14, cosalette ADR-057/ADR-059).  The
    ``state``/``brightness``/``hsb``/``effect`` fields additionally carry
    ``consumer()`` + ``openhab()`` metadata driving the offline openHAB
    Generic MQTT Thing generation.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=ha_entities(
            _HA_LIGHT_ENTITY,
            _HA_POWER_SENSOR_ENTITY,
            _HA_EFFECT_SPEED_ENTITY,
        ),
    )

    state: Annotated[
        Literal["ON", "OFF"] | None,
        Field(
            default=None,
            json_schema_extra=merge(
                consumer(display_name="State"),
                openhab(
                    item_type="Switch",
                    channel_type="switch",
                    channel_params={"on": _OPENHAB_ON, "off": _OPENHAB_OFF},
                ),
            ),
        ),
    ] = None
    brightness: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            le=255,
            json_schema_extra=merge(
                consumer(display_name="Brightness"),
                openhab(
                    item_type="Dimmer",
                    channel_type="dimmer",
                    channel_params={
                        "min": 0,
                        "max": 255,
                        "step": 1,
                        "on": _OPENHAB_ON,
                        "off": _OPENHAB_OFF,
                    },
                ),
            ),
        ),
    ] = None
    color_mode: Literal["color_temp", "rgb"] | None = None
    color: BulbColor | None = None
    color_temp: int | None = None
    color_temp_kelvin: bool | None = None
    hsb: Annotated[
        str | None,
        Field(
            default=None,
            json_schema_extra=merge(
                consumer(display_name="Color"),
                openhab(
                    item_type="Color",
                    channel_type="color",
                    channel_params={
                        "colorMode": "HSB",
                        "on": _OPENHAB_ON,
                        "off": _OPENHAB_OFF,
                    },
                ),
            ),
        ),
    ] = None
    effect: Annotated[
        int | None,
        Field(
            default=None,
            json_schema_extra=merge(
                consumer(display_name="Effect"),
                openhab(item_type="String", channel_type="string"),
            ),
        ),
    ] = None
    effect_speed: int | None = None
    power_draw_w: float | None = None


class BulbSetCommand(BaseModel):
    """Inbound ``.../set`` payload — HA's JSON light schema, every field optional.

    HA sends multi-field payloads (``{"state": "ON", "brightness": 128}``);
    openHAB's ``formatBeforePublish`` sends single-field payloads. Every
    field defaults to ``None`` so both are valid partial updates.

    ``color``, ``color_temp``, ``effect`` and ``hsb`` are mutually
    exclusive.  This cannot be enforced downstream: ``pywizlight`` never
    raises on conflicting kwargs — rgb+scene silently merges both onto one
    pilot (firmware race), and rgb+colortemp silently drops temp by fixed
    source-order priority regardless of kwarg order. Validating here
    rejects the whole payload instead of picking a winner.

    The model carries the same composite HA ``light``/``number`` entity
    specs as :class:`BulbStateModel`; the discovery generator merges this
    receive (``/set``) channel with the send (``/state``) channel into one
    entity, contributing the ``command_topic`` half (cosalette ADR-057).
    ``state``/``brightness``/``hsb``/``effect`` also carry ``openhab()``
    metadata so the offline openHAB Thing gets a command channel per field
    on the shared ``/set`` topic.
    """

    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra=ha_entities(_HA_LIGHT_ENTITY, _HA_EFFECT_SPEED_ENTITY),
    )

    state: Annotated[
        Literal["ON", "OFF"] | None,
        Field(
            default=None,
            json_schema_extra=merge(
                consumer(display_name="State"),
                openhab(
                    item_type="Switch",
                    channel_type="switch",
                    channel_params={"on": _OPENHAB_ON, "off": _OPENHAB_OFF},
                ),
            ),
        ),
    ] = None
    brightness: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=255,
            json_schema_extra=merge(
                consumer(display_name="Brightness"),
                openhab(
                    item_type="Dimmer",
                    channel_type="dimmer",
                    channel_params={
                        "min": 0,
                        "max": 255,
                        "step": 1,
                        "on": _OPENHAB_ON,
                        "off": _OPENHAB_OFF,
                    },
                ),
            ),
        ),
    ] = None
    color: BulbColor | None = None
    color_temp: int | None = Field(default=None, gt=0, le=10000)
    effect: Annotated[
        int | None,
        Field(
            default=None,
            ge=1,
            le=1000,
            json_schema_extra=merge(
                consumer(display_name="Effect"),
                openhab(item_type="String", channel_type="string"),
            ),
        ),
    ] = None
    hsb: Annotated[
        str | None,
        Field(
            default=None,
            json_schema_extra=merge(
                consumer(display_name="Color"),
                openhab(
                    item_type="Color",
                    channel_type="color",
                    channel_params={
                        "colorMode": "HSB",
                        "on": _OPENHAB_ON,
                        "off": _OPENHAB_OFF,
                    },
                ),
            ),
        ),
    ] = None
    effect_speed: int | None = Field(
        default=None, ge=_EFFECT_SPEED_MIN, le=_EFFECT_SPEED_MAX
    )

    @model_validator(mode="after")
    def _at_most_one_color_mode(self) -> BulbSetCommand:
        modes = (self.color, self.color_temp, self.effect, self.hsb)
        if not any(m is not None for m in modes):
            return self
        if sum(m is not None for m in modes) > 1:
            raise ValueError("color, color_temp, effect and hsb are mutually exclusive")
        return self
