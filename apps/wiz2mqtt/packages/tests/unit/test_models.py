"""Unit tests for models.py — payload validation + discovery metadata ,
.

Test Techniques Used:
- Equivalence Partitioning: valid single-field, multi-field, and empty payloads
- Boundary Value Analysis: brightness 0-255 (0 = OFF), color channels 0-255,
  effect_speed 10-200
- Decision Table: color/color_temp/effect/hsb mutual exclusion combinations
- State Transition Testing: BulbState.apply_command colour-mode transitions
- Error Guessing: extra/unknown fields, out-of-range values
- Specification-based: the HA ``ha_entities`` discovery metadata each model carries
"""

from __future__ import annotations

from typing import Any

import jinja2
import pytest
from pydantic import ValidationError

from wiz2mqtt.models import (
    NULL_WIRE,
    POWER_REQUEST_INACTIVE,
    WIZ_EFFECT_LIST,
    BulbSetCommand,
    BulbState,
    BulbStateModel,
    PowerSourceStateModel,
)

# ---------------------------------------------------------------------------
# Partial updates — every field optional
# ---------------------------------------------------------------------------


class TestPartialUpdates:
    """Every field is optional, matching HA's multi-field and openHAB's
    single-field payload conventions.
    """

    def test_models_empty_payload_is_valid(self) -> None:
        """An empty object is a valid (no-op) partial update.

        Technique: Equivalence Partitioning — the all-None case.
        """
        cmd = BulbSetCommand()
        assert cmd.state is None
        assert cmd.brightness is None
        assert cmd.color is None
        assert cmd.color_temp is None
        assert cmd.effect is None

    def test_models_single_field_state_only(self) -> None:
        """A single-field ``state`` payload (openHAB style) parses cleanly.

        Technique: Equivalence Partitioning — single-field partial update.
        """
        cmd = BulbSetCommand.model_validate({"state": "ON"})
        assert cmd.state == "ON"
        assert cmd.brightness is None

    def test_models_multi_field_ha_style_payload(self) -> None:
        """A multi-field HA-style payload parses every given field.

        Technique: Specification-based — HA's documented wire example.
        """
        cmd = BulbSetCommand.model_validate({"state": "ON", "brightness": 128})
        assert cmd.state == "ON"
        assert cmd.brightness == 128

    def test_models_unknown_extra_fields_are_ignored(self) -> None:
        """Unknown fields (e.g. future HA keys) don't reject the payload.

        Technique: Error Guessing — forward-compatibility with unknown keys.
        """
        cmd = BulbSetCommand.model_validate({"state": "ON", "unexpected": True})
        assert cmd.state == "ON"


# ---------------------------------------------------------------------------
# Field validation
# ---------------------------------------------------------------------------


class TestFieldValidation:
    """Boundary and type validation for individual fields."""

    @pytest.mark.parametrize("value", ["ON", "OFF"])
    def test_models_state_accepts_on_off(self, value: str) -> None:
        """Only the literal ON/OFF strings are accepted for state.

        Technique: Equivalence Partitioning — valid state values.
        """
        cmd = BulbSetCommand.model_validate({"state": value})
        assert cmd.state == value

    def test_models_state_rejects_invalid_value(self) -> None:
        """A state value outside ON/OFF is rejected.

        Technique: Error Guessing — invalid enum value.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"state": "TOGGLE"})

    @pytest.mark.parametrize("value", [0, 1, 128, 255])
    def test_models_brightness_accepts_in_range(self, value: int) -> None:
        """Brightness within 0-255 is accepted; 0 is the openHAB OFF command.

        Technique: Boundary Value Analysis — lower/mid/upper bounds.
        """
        cmd = BulbSetCommand.model_validate({"brightness": value})
        assert cmd.brightness == value

    @pytest.mark.parametrize("value", [256, -1])
    def test_models_brightness_rejects_out_of_range(self, value: int) -> None:
        """Brightness outside 0-255 is rejected.

        Technique: Boundary Value Analysis — just outside both bounds.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"brightness": value})

    def test_models_color_accepts_valid_rgb(self) -> None:
        """A well-formed {r,g,b} object is accepted.

        Technique: Specification-based — HA's color object shape.
        """
        cmd = BulbSetCommand.model_validate({"color": {"r": 255, "g": 0, "b": 128}})
        assert cmd.color is not None
        assert (cmd.color.r, cmd.color.g, cmd.color.b) == (255, 0, 128)

    @pytest.mark.parametrize("channel", ["r", "g", "b"])
    def test_models_color_rejects_out_of_range_channel(self, channel: str) -> None:
        """Each RGB channel is bounded to 0-255.

        Technique: Boundary Value Analysis — one out-of-range channel.
        """
        payload = {"color": {c: 256 if c == channel else 0 for c in ("r", "g", "b")}}
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate(payload)

    def test_models_color_temp_rejects_zero(self) -> None:
        """color_temp must be strictly positive (Kelvin).

        Technique: Boundary Value Analysis — zero is invalid.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"color_temp": 0})

    def test_models_color_temp_accepts_minimum_positive_value(self) -> None:
        """color_temp=1 is the minimum valid value (strictly above zero).

        Technique: Boundary Value Analysis — just-inside lower bound (gt=0).
        """
        cmd = BulbSetCommand.model_validate({"color_temp": 1})
        assert cmd.color_temp == 1

    def test_models_color_temp_accepts_maximum_value(self) -> None:
        """color_temp=10000 is the pywizlight hard ceiling, must be accepted.

        Technique: Boundary Value Analysis — upper bound (le=10000).
        """
        cmd = BulbSetCommand.model_validate({"color_temp": 10000})
        assert cmd.color_temp == 10000

    def test_models_color_temp_rejects_above_maximum(self) -> None:
        """color_temp above 10000 is rejected.

        Technique: Boundary Value Analysis — just outside upper bound.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"color_temp": 10001})

    def test_models_effect_accepts_known_scene_name(self) -> None:
        """A scene name from the advertised ``effect_list`` is accepted.

        Technique: Equivalence Partitioning — the valid-name class.
        """
        cmd = BulbSetCommand.model_validate({"effect": "Ocean"})
        assert cmd.effect == "Ocean"

    def test_models_effect_rejects_unknown_scene_name(self) -> None:
        """A name absent from ``WIZ_EFFECT_LIST`` is rejected at the boundary.

        Technique: Equivalence Partitioning — the invalid-name class. HA only
        sends advertised names, but an openHAB String item can send anything.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect": "Nonexistent Scene"})

    def test_models_effect_rejects_numeric_scene_id(self) -> None:
        """A bare numeric scene id is no longer a valid wire value (ADR-001).

        Technique: Error Guessing — the pre-name-translation wire shape.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect": 7})

    @pytest.mark.parametrize("value", [10, 100, 200])
    def test_models_effect_speed_accepts_in_range(self, value: int) -> None:
        """effect_speed within pywizlight's 10-200 range is accepted.

        Technique: Boundary Value Analysis — lower/mid/upper bounds.
        """
        cmd = BulbSetCommand.model_validate({"effect_speed": value})
        assert cmd.effect_speed == value

    @pytest.mark.parametrize("value", [9, 201, 0, -1])
    def test_models_effect_speed_rejects_out_of_range(self, value: int) -> None:
        """effect_speed outside 10-200 is rejected (pywizlight raises otherwise).

        Technique: Boundary Value Analysis — just outside both bounds.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect_speed": value})

    def test_models_hsb_accepts_string(self) -> None:
        """hsb is a free-form ``"h,s,b"`` string (openHAB Color channel wire form).

        Technique: Equivalence Partitioning — the string-typed colour input.
        """
        cmd = BulbSetCommand.model_validate({"hsb": "120,100,50"})
        assert cmd.hsb == "120,100,50"


# ---------------------------------------------------------------------------
# Fractional floats on the integer command fields
# ---------------------------------------------------------------------------


class TestFractionalNumbers:
    """A fractional float on an integer ``.../set`` field rounds, never drops.

    openHAB's Dimmer channel maps a percent command onto the advertised
    ``min``/``max`` as ``pct / 100 * 255``, integral only at multiples of
    20 % — so almost every real dimmer command used to be rejected with
    ``type=int_from_float`` and published to the error topic instead.
    """

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(76.47, 76), (76.0, 76), (255.4, 255), (1.4, 1), (254.5, 254)],
    )
    def test_models_brightness_rounds_a_fractional_float(
        self, value: float, expected: int
    ) -> None:
        """A fractional brightness rounds to the nearest whole number.

        Technique: Boundary Value Analysis — inside the range, with the
        banker's-rounding tie (254.5 -> 254) pinned down.
        """
        cmd = BulbSetCommand.model_validate({"brightness": value})
        assert cmd.brightness == expected

    @pytest.mark.parametrize("value", [-0.6, 256.4, 255.5, "76.47"])
    def test_models_brightness_still_rejects_out_of_range_or_non_numeric(
        self, value: object
    ) -> None:
        """Rounding runs before the range check and never rescues a bad value.

        Technique: Boundary Value Analysis / Error Guessing — -0.6 rounds to -1
        and 255.5 up to 256 (banker's rounding), both outside 0-255; a string
        is not coerced at all.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"brightness": value})

    @pytest.mark.parametrize("field", ["brightness", "color_temp", "effect_speed"])
    @pytest.mark.parametrize("value", [False, True, "0", "128"])
    def test_models_lenient_field_rejects_a_bool_or_numeric_string(
        self, field: str, value: object
    ) -> None:
        """Only a JSON number reaches an integer command field.

        Technique: Error Guessing — lax ``int`` turns ``false`` or ``"0"``
        into brightness 0, which means OFF, so a templating mistake would
        switch the bulb off instead of reaching the error topic.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({field: value})

    @pytest.mark.parametrize("literal", ["Infinity", "-Infinity", "NaN"])
    def test_models_brightness_rejects_a_non_finite_number(self, literal: str) -> None:
        """A non-finite JSON number is a validation error, not a crash.

        Technique: Error Guessing — ``round(inf)`` raises ``OverflowError``,
        which Pydantic would let escape instead of reporting it.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate_json(f'{{"brightness": {literal}}}')

    def test_models_brightness_accepts_an_explicit_null(self) -> None:
        """An explicit ``null`` still means "field not given".

        Technique: Error Guessing — the regression the lenient annotation
        must not introduce (constraints beside a ``BeforeValidator`` on the
        ``int | None`` union raise ``TypeError`` for ``None``).
        """
        cmd = BulbSetCommand.model_validate({"brightness": None})
        assert cmd.brightness is None

    def test_models_color_temp_rounds_a_fractional_float(self) -> None:
        """color_temp shares brightness's lenient coercion.

        Technique: Equivalence Partitioning — the same class, other field.
        """
        assert BulbSetCommand.model_validate({"color_temp": 2699.6}).color_temp == 2700

    def test_models_color_temp_still_rejects_a_rounded_out_of_range_value(self) -> None:
        """A fractional color_temp above the ceiling stays rejected.

        Technique: Boundary Value Analysis — 10000.6 rounds to 10001.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"color_temp": 10000.6})

    def test_models_effect_speed_rounds_a_fractional_float(self) -> None:
        """effect_speed shares brightness's lenient coercion.

        Technique: Equivalence Partitioning — the same class, other field.
        """
        assert BulbSetCommand.model_validate({"effect_speed": 99.6}).effect_speed == 100

    def test_models_effect_speed_still_rejects_a_rounded_out_of_range_value(
        self,
    ) -> None:
        """A fractional effect_speed below the floor stays rejected.

        Technique: Boundary Value Analysis — 9.4 rounds to 9.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect_speed": 9.4})

    @pytest.mark.parametrize(
        ("field", "bounds"),
        [
            ("brightness", {"minimum": 0, "maximum": 255}),
            ("color_temp", {"exclusiveMinimum": 0, "maximum": 10000}),
            ("effect_speed", {"minimum": 10, "maximum": 200}),
        ],
    )
    def test_models_lenient_field_keeps_json_schema_bounds(
        self, field: str, bounds: dict[str, int]
    ) -> None:
        """The generated schema still carries the bounds on the integer branch.

        Technique: Specification-based — the published AsyncAPI contract
        (docs/schema.yaml) must not drift; a constraint declared beside the
        ``BeforeValidator`` would emit ``ge``/``le`` at the field level instead.
        """
        prop = BulbSetCommand.model_json_schema()["properties"][field]
        integer_branch = next(
            branch for branch in prop["anyOf"] if branch.get("type") == "integer"
        )
        assert integer_branch == {"type": "integer", **bounds}


# ---------------------------------------------------------------------------
# Mutual exclusion — color / color_temp / effect
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    """color, color_temp, effect and hsb must never co-occur in one payload."""

    def test_models_color_alone_is_valid(self) -> None:
        """color with no color_temp/effect/hsb is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"color": {"r": 1, "g": 2, "b": 3}})
        assert cmd.color is not None

    def test_models_color_temp_alone_is_valid(self) -> None:
        """color_temp with no color/effect/hsb is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"color_temp": 3000})
        assert cmd.color_temp == 3000

    def test_models_effect_alone_is_valid(self) -> None:
        """effect with no color/color_temp/hsb is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"effect": "Forest"})
        assert cmd.effect == "Forest"

    def test_models_hsb_alone_is_valid(self) -> None:
        """hsb with no color/color_temp/effect is a valid payload.

        Technique: Decision Table — single field set, others None. openHAB's
        Color channel sends ``hsb`` on its own via ``formatBeforePublish``.
        """
        cmd = BulbSetCommand.model_validate({"hsb": "200,80,60"})
        assert cmd.hsb == "200,80,60"

    @pytest.mark.parametrize(
        "payload",
        [
            {"color": {"r": 1, "g": 2, "b": 3}, "color_temp": 3000},
            {"color": {"r": 1, "g": 2, "b": 3}, "effect": "Forest"},
            {"color_temp": 3000, "effect": "Forest"},
            {"color": {"r": 1, "g": 2, "b": 3}, "hsb": "1,2,3"},
            {"color_temp": 3000, "hsb": "1,2,3"},
            {"effect": "Forest", "hsb": "1,2,3"},
            {"color": {"r": 1, "g": 2, "b": 3}, "color_temp": 3000, "effect": "Forest"},
            {
                "color": {"r": 1, "g": 2, "b": 3},
                "color_temp": 3000,
                "effect": "Forest",
                "hsb": "1,2,3",
            },
        ],
        ids=[
            "color+color_temp",
            "color+effect",
            "color_temp+effect",
            "color+hsb",
            "color_temp+hsb",
            "effect+hsb",
            "color+color_temp+effect",
            "all_four",
        ],
    )
    def test_models_rejects_conflicting_combinations(
        self, payload: dict[str, object]
    ) -> None:
        """Any two-or-more-way overlap between the four colour fields is rejected.

        Technique: Decision Table — every conflicting combination whole-payload
        rejected (not merged, not one field silently dropped).
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate(payload)

    def test_models_state_and_brightness_do_not_trigger_exclusion(self) -> None:
        """state/brightness are unaffected by the color/color_temp/effect check.

        Technique: Error Guessing — confirm the validator is scoped correctly.
        """
        cmd = BulbSetCommand.model_validate(
            {"state": "ON", "brightness": 200, "color_temp": 4000}
        )
        assert cmd.state == "ON"
        assert cmd.brightness == 200
        assert cmd.color_temp == 4000


# ---------------------------------------------------------------------------
# BulbState.apply_command — mode-aware optimistic merge
# ---------------------------------------------------------------------------


def _state(**overrides: object) -> BulbState:
    """Build a BulbState with every field defaulted to None, overridden as given."""
    defaults: dict[str, object] = {
        "state": None,
        "brightness": None,
        "hue": None,
        "saturation": None,
        "color_temp_kelvin": None,
        "scene": None,
    }
    defaults.update(overrides)
    return BulbState(**defaults)  # type: ignore[arg-type]


class TestApplyCommand:
    """apply_command clears a superseded colour mode instead of only adding fields."""

    def test_apply_command_colour_clears_color_temp(self) -> None:
        """CCT to colour: giving hue/saturation clears color_temp_kelvin.

        Technique: State Transition Testing — CCT mode to RGB mode.
        """
        current = _state(color_temp_kelvin=2700)
        updated = current.apply_command(hue=0.0, saturation=100.0)
        assert updated.color_temp_kelvin is None
        assert updated.hue == 0.0
        assert updated.saturation == 100.0

    def test_apply_command_color_temp_clears_colour(self) -> None:
        """Colour to CCT: giving color_temp_kelvin clears hue/saturation.

        Technique: State Transition Testing — RGB mode to CCT mode.
        """
        current = _state(hue=0.0, saturation=100.0)
        updated = current.apply_command(color_temp_kelvin=2700)
        assert updated.hue is None
        assert updated.saturation is None
        assert updated.color_temp_kelvin == 2700

    def test_apply_command_colour_clears_scene(self) -> None:
        """Scene to colour: giving hue/saturation clears scene.

        Technique: State Transition Testing — scene mode to RGB mode.
        """
        current = _state(scene=1)
        updated = current.apply_command(hue=0.0, saturation=100.0)
        assert updated.scene is None
        assert updated.hue == 0.0
        assert updated.saturation == 100.0

    def test_apply_command_hue_only_preserves_color_temp(self) -> None:
        """A partial colour update does not supersede CCT mode."""
        current = _state(color_temp_kelvin=2700)
        updated = current.apply_command(hue=0.0)
        assert updated == current

    def test_apply_command_saturation_only_preserves_scene(self) -> None:
        """A partial colour update does not supersede scene mode."""
        current = _state(scene=1)
        updated = current.apply_command(saturation=100.0)
        assert updated == current

    def test_apply_command_scene_clears_colour(self) -> None:
        """Colour to scene: giving scene clears hue/saturation.

        Technique: State Transition Testing — RGB mode to scene mode.
        """
        current = _state(hue=0.0, saturation=100.0)
        updated = current.apply_command(scene=1)
        assert updated.hue is None
        assert updated.saturation is None
        assert updated.scene == 1

    def test_apply_command_no_colour_field_leaves_mode_untouched(self) -> None:
        """A command touching only brightness leaves the colour mode alone.

        Technique: Equivalence Partitioning — non-colour update.
        """
        current = _state(color_temp_kelvin=2700)
        updated = current.apply_command(brightness=42)
        assert updated.color_temp_kelvin == 2700
        assert updated.brightness == 42

    def test_apply_command_state_and_brightness_keep_additive_semantics(self) -> None:
        """state/brightness/effect_speed only apply when given, like before.

        Technique: Specification-based — non-colour fields unaffected.
        """
        current = _state(state=True, brightness=100)
        updated = current.apply_command(brightness=None)
        assert updated.state is True
        assert updated.brightness == 100


class TestApplySetState:
    """apply_set_state merges a ``set_state`` call's kwargs (speed -> effect_speed)."""

    def test_off_merges_only_the_state_field(self) -> None:
        """Technique: Specification-based — turn_off() carries no appearance."""
        current = _state(state=True, brightness=200)

        updated = current.apply_set_state({"state": False, "brightness": 50})

        assert updated.state is False
        assert updated.brightness == 200

    def test_speed_maps_onto_effect_speed(self) -> None:
        updated = _state(state=True).apply_set_state({"speed": 120, "brightness": 90})

        assert updated.effect_speed == 120
        assert updated.brightness == 90

    def test_none_values_leave_fields_untouched(self) -> None:
        """Technique: Equivalence Partitioning — unset kwargs are the None class."""
        current = _state(state=True, brightness=200)

        updated = current.apply_set_state({"state": None, "brightness": None})

        assert updated == current


# ---------------------------------------------------------------------------
# Home Assistant discovery metadata
# ---------------------------------------------------------------------------


def _ha_entities(model: type) -> list[dict[str, object]]:
    """The composite HA entity specs a payload model declares on its config."""
    schema = model.model_json_schema()
    return schema["x-cosalette-ha-discovery"]["entities"]


def _openhab(
    model: type[BulbStateModel | BulbSetCommand], field: str
) -> dict[str, Any]:
    """The ``openhab()`` channel metadata one payload field declares."""
    return model.model_json_schema()["properties"][field]["x-cosalette-openhab"]


class TestHaDiscoveryMetadata:
    """Both payload models carry ``ha_entities`` metadata the discovery
    generator (and ``app.discovery()``) turn into per-bulb HA entities.
    """

    def test_models_state_model_declares_light_and_diagnostics(self) -> None:
        """The state payload spans a light, power sensor, speed and readiness.

        Technique: Specification-based — the per-bulb components the state
        topic feeds: light, power, speed, then reachable/pending/last_applied.
        """
        components = [e["component"] for e in _ha_entities(BulbStateModel)]
        assert components == [
            "light",
            "sensor",
            "number",
            "binary_sensor",
            "sensor",
            "sensor",
        ]

    def test_models_set_command_declares_light_and_number_only(self) -> None:
        """The command payload has no read-only power sensor — light + number.

        Technique: Specification-based — the ``/set`` half contributes the
        command topic to the light and speed number, never the sensor.
        """
        components = [e["component"] for e in _ha_entities(BulbSetCommand)]
        assert components == ["light", "number"]

    def test_models_light_entity_is_json_schema_with_full_capability_superset(
        self,
    ) -> None:
        """The light advertises schema:json, brightness, the static colour-mode
        superset, the full WiZ scene list and the fixed 2200-6500 K range.

        Technique: Specification-based — Option A static wire-format superset
        (per-bulb capability filtering deferred, see the TOML-inventory ADR).
        """
        light = next(
            e for e in _ha_entities(BulbStateModel) if e["component"] == "light"
        )
        extra = light["extra"]
        assert extra["schema"] == "json"
        assert extra["brightness"] is True
        assert extra["supported_color_modes"] == ["color_temp", "rgb"]
        assert extra["effect"] is True
        assert tuple(extra["effect_list"]) == WIZ_EFFECT_LIST
        assert (extra["min_kelvin"], extra["max_kelvin"]) == (2200, 6500)

    def test_models_power_sensor_entity_carries_power_device_class(self) -> None:
        """The power sensor reads ``value_json.power_draw_w`` in watts.

        Technique: Specification-based — HA ``sensor`` measurement contract.
        """
        sensor = next(
            e for e in _ha_entities(BulbStateModel) if e["component"] == "sensor"
        )
        assert sensor["name"] == "Power"
        assert sensor["extra"]["device_class"] == "power"
        assert sensor["extra"]["unit_of_measurement"] == "W"
        assert sensor["extra"]["state_class"] == "measurement"
        assert sensor["extra"]["value_template"] == "{{ value_json.power_draw_w }}"

    def test_models_effect_speed_number_entity_is_bounded_slider(self) -> None:
        """The effect-speed number is a 10-200 slider shaping a JSON command.

        Technique: Boundary Value Analysis — the min/max/step the number
        entity advertises match pywizlight's accepted ``speed`` range.
        """
        number = next(
            e for e in _ha_entities(BulbStateModel) if e["component"] == "number"
        )
        assert number["name"] == "Effect speed"
        extra = number["extra"]
        assert (extra["min"], extra["max"], extra["step"]) == (10, 200, 1)
        assert extra["command_template"] == '{"effect_speed": {{ value }}}'
        assert extra["value_template"] == "{{ value_json.effect_speed }}"

    @pytest.mark.parametrize(
        "field, expected_channel_type",
        [
            ("state", "switch"),
            ("brightness", "dimmer"),
            ("hsb", "color"),
            ("effect", "string"),
        ],
    )
    def test_models_state_fields_carry_openhab_channel_metadata(
        self, field: str, expected_channel_type: str
    ) -> None:
        """state/brightness/hsb/effect carry ``openhab()`` channel metadata for
        the offline Generic MQTT Thing generation.

        Technique: Decision Table — one openHAB channel type per wire field.
        """
        assert _openhab(BulbStateModel, field)["channel_type"] == expected_channel_type

    def test_models_switch_on_off_are_plain_state_values(self) -> None:
        """openHAB formats a Switch's ``on``/``off`` through
        ``formatBeforePublish`` — so they must be the bare ``ON``/``OFF``.

        Technique: Error Guessing — a JSON ``on`` value ends up nested as
        ``{"state":"{"state": "ON"}"}``, which the ``/set`` validator rejects.
        """
        for model in (BulbStateModel, BulbSetCommand):
            meta = _openhab(model, "state")
            assert meta["channel_params"]["on"] == "ON"
            assert meta["channel_params"]["off"] == "OFF"

    @pytest.mark.parametrize("field", ["brightness", "hsb"])
    def test_models_dimmer_and_color_carry_no_on_off_values(self, field: str) -> None:
        """A Dimmer or Color channel needs no ``on``/``off``: openHAB turns
        OFF into brightness 0, which ``/set`` treats as OFF.

        Technique: Error Guessing — with ``on``/``off`` set, a Dimmer publishes
        the string into ``{"brightness":%s}`` and the command is rejected.
        """
        params = _openhab(BulbSetCommand, field)["channel_params"]
        assert "on" not in params
        assert "off" not in params

    def test_models_hsb_format_uses_all_three_color_arguments(self) -> None:
        """Color commands publish the HSB triple, including brightness zero."""
        assert (
            _openhab(BulbSetCommand, "hsb")["channel_params"]["formatBeforePublish"]
            == '{"hsb":"%1$d,%2$d,%3$d"}'
        )

    def test_models_dimmer_min_matches_command_brightness_floor(self) -> None:
        """The openHAB dimmer ``min`` matches ``brightness`` ``ge=0``.

        A generated openHAB config must never be able to emit a brightness the
        ``/set`` validator would reject.

        Technique: Specification-based — metadata/validation consistency
        (PR #238 review finding).
        """
        for model in (BulbStateModel, BulbSetCommand):
            params = _openhab(model, "brightness")["channel_params"]
            assert (params["min"], params["max"]) == (0, 255)

    @pytest.mark.parametrize(
        ("field", "bounds"),
        [("color_temp", (2200, 6500)), ("effect_speed", (10, 200))],
    )
    def test_models_number_channels_are_bounded(
        self, field: str, bounds: tuple[int, int]
    ) -> None:
        """Colour temperature and effect speed are bounded Number channels
        with a command half.

        Technique: Boundary Value Analysis — the advertised range matches the
        bulbs' kelvin range and pywizlight's ``speed`` range.
        """
        for model in (BulbStateModel, BulbSetCommand):
            meta = _openhab(model, field)
            assert meta["item_type"] == "Number"
            params = meta["channel_params"]
            assert (params["min"], params["max"], params["step"]) == (*bounds, 1)

    def test_models_power_draw_is_read_only_watts(self) -> None:
        """``power_draw_w`` is a state-only Number labelled in watts.

        Technique: Specification-based — a diagnostic has no command half.
        """
        prop = BulbStateModel.model_json_schema()["properties"]["power_draw_w"]
        assert _openhab(BulbStateModel, "power_draw_w")["item_type"] == "Number"
        assert prop["x-cosalette-consumer"]["unit"] == "W"
        assert prop["x-cosalette-consumer"]["read_only"] is True
        assert "power_draw_w" not in BulbSetCommand.model_fields

    def test_models_effect_command_lists_the_scene_names(self) -> None:
        """The effect command channel offers exactly the WiZ scene list.

        Technique: Specification-based — openHAB ``allowedStates``.
        """
        params = _openhab(BulbSetCommand, "effect")["channel_params"]
        assert params["allowedStates"].split(",") == list(WIZ_EFFECT_LIST)


class TestPoweredField:
    """``BulbStateModel.powered`` — required, no default (ADR-001 amendment)."""

    def test_powered_is_required(self) -> None:
        """Technique: Error Guessing — a publish that forgets ``powered`` is a bug."""
        with pytest.raises(ValidationError):
            BulbStateModel.model_validate({"state": "ON"})

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(True, True), (False, False), ("__unknown__", None)],
    )
    def test_powered_accepts_bool_or_the_sentinel(
        self, value: bool | str, expected: bool | None
    ) -> None:
        model = BulbStateModel.model_validate({"state": "ON", "powered": value})
        assert model.model_dump(mode="json", exclude_none=True)["powered"] == expected

    def test_powered_rejects_an_arbitrary_string(self) -> None:
        with pytest.raises(ValidationError):
            BulbStateModel.model_validate({"state": "ON", "powered": "unknown"})


class TestPowerSourceStateModel:
    """The retained per-source payload (ADR-007 amendment) — cap-bjw9.7."""

    def test_accepts_the_full_shape(self) -> None:
        model = PowerSourceStateModel.model_validate(
            {
                "powered": "on",
                "power_request": POWER_REQUEST_INACTIVE,
                "members": ["desk", "lamp"],
            }
        )
        assert model.powered == "on"
        assert model.members == ["desk", "lamp"]

    def test_rejects_an_unknown_powered_value(self) -> None:
        with pytest.raises(ValidationError):
            PowerSourceStateModel.model_validate({"powered": "maybe", "members": []})

    def test_declares_two_binary_sensor_entities(self) -> None:
        """cap-bjw9.10 — the belief and the desired power, never a switch."""
        extra = PowerSourceStateModel.model_config.get("json_schema_extra")
        assert extra is not None
        entities = extra["x-cosalette-ha-discovery"]["entities"]
        assert len(entities) == 2
        assert {entity["component"] for entity in entities} == {"binary_sensor"}

    def test_belief_entity_has_power_device_class(self) -> None:
        extra = PowerSourceStateModel.model_config["json_schema_extra"]
        entities = extra["x-cosalette-ha-discovery"]["entities"]
        belief = next(e for e in entities if e["name"] == "powered")
        assert belief["extra"]["device_class"] == "power"

    @pytest.mark.parametrize(
        ("powered", "rendered"),
        [("on", "ON"), ("off", "OFF"), ("unknown", "None")],
    )
    def test_belief_template_keeps_unknown_distinct_from_off(
        self, powered: str, rendered: str
    ) -> None:
        """An unknown belief must not read as a dark circuit.

        Technique: Equivalence Partitioning — one case per belief value.
        ``None`` is the payload Home Assistant reads as an unknown state.
        """
        extra = PowerSourceStateModel.model_config["json_schema_extra"]
        entities = extra["x-cosalette-ha-discovery"]["entities"]
        belief = next(e for e in entities if e["name"] == "powered")

        template = jinja2.Environment(autoescape=True).from_string(
            belief["extra"]["value_template"]
        )

        assert template.render(value_json={"powered": powered}) == rendered

    def test_power_request_entity_is_diagnostic(self) -> None:
        extra = PowerSourceStateModel.model_config["json_schema_extra"]
        entities = extra["x-cosalette-ha-discovery"]["entities"]
        request = next(e for e in entities if e["name"] == "power_request")
        assert request["extra"]["entity_category"] == "diagnostic"

    def test_inactive_power_request_serializes_as_null(self) -> None:
        model = PowerSourceStateModel.model_validate(
            {"powered": "unknown", "members": []}
        )
        assert model.model_dump(mode="json", exclude_none=True)["power_request"] is None

    def test_power_request_rejects_raw_null(self) -> None:
        """Technique: Error Guessing — only the internal sentinel is inactive."""
        with pytest.raises(ValidationError):
            PowerSourceStateModel.model_validate(
                {"powered": "unknown", "power_request": None, "members": []}
            )


class TestReadinessFields:
    """``reachable``/``pending``/``last_applied`` on the bulb state (cap-ea7n.3)."""

    _PENDING = {"fields": ["state", "brightness"], "queued_at": 100, "expires_at": 400}
    _APPLIED = {"at": 500, "fields": ["state"], "attempts": 1, "confirmed": True}

    def _dump(self, **fields: object) -> dict[str, object]:
        model = BulbStateModel.model_validate(
            {"state": "ON", "powered": True, **fields}
        )
        return model.model_dump(mode="json", exclude_none=True)

    def test_absent_pending_and_last_applied_serialize_as_null(self) -> None:
        """The keys stay on the wire as ``null`` so openHAB clears its Items.

        Technique: Error Guessing — ``exclude_none`` would otherwise drop the
        keys and leave a consumer holding the previous command.
        """
        dumped = self._dump(pending=NULL_WIRE, last_applied=NULL_WIRE)
        assert dumped["pending"] is None
        assert dumped["last_applied"] is None

    def test_present_readiness_round_trips(self) -> None:
        """Technique: Round-trip Testing — objects pass through unchanged."""
        dumped = self._dump(
            reachable=False, pending=self._PENDING, last_applied=self._APPLIED
        )
        assert dumped["reachable"] is False
        assert dumped["pending"] == self._PENDING
        assert dumped["last_applied"] == self._APPLIED

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("pending", None),
            ("pending", {**_PENDING, "extra": 1}),
            ("last_applied", {**_APPLIED, "attempts": 0}),
        ],
    )
    def test_rejects_malformed_readiness(self, field: str, value: object) -> None:
        """Technique: Error Guessing — raw ``null``, unknown keys, zero attempts."""
        with pytest.raises(ValidationError):
            self._dump(**{field: value})

    @pytest.mark.parametrize(
        ("name", "value_json", "rendered"),
        [
            ("Reachable", {"reachable": True}, "ON"),
            ("Reachable", {"reachable": False}, "OFF"),
            ("Pending", {"pending": None}, "none"),
            ("Pending", {"pending": _PENDING}, "state,brightness"),
            ("Last applied", {"last_applied": None}, "none"),
            ("Last applied", {"last_applied": _APPLIED}, "confirmed"),
            (
                "Last applied",
                {"last_applied": {**_APPLIED, "confirmed": False}},
                "unconfirmed",
            ),
        ],
    )
    def test_ha_templates_render_every_state(
        self, name: str, value_json: dict[str, object], rendered: str
    ) -> None:
        """Technique: Equivalence Partitioning — one case per wire state."""
        entity = next(e for e in _ha_entities(BulbStateModel) if e.get("name") == name)
        template = jinja2.Environment(autoescape=True).from_string(
            entity["extra"]["value_template"]
        )
        assert template.render(value_json=value_json) == rendered
