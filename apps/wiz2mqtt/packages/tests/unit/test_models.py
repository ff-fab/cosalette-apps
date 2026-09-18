"""Unit tests for models.py — payload validation + discovery metadata ,
.

Test Techniques Used:
- Equivalence Partitioning: valid single-field, multi-field, and empty payloads
- Boundary Value Analysis: brightness 1-255, color channels 0-255, effect_speed 10-200
- Decision Table: color/color_temp/effect/hsb mutual exclusion combinations
- State Transition Testing: BulbState.apply_command colour-mode transitions
- Error Guessing: extra/unknown fields, out-of-range values
- Specification-based: the HA ``ha_entities`` discovery metadata each model carries
"""

from __future__ import annotations

import jinja2
import pytest
from pydantic import ValidationError

from wiz2mqtt.models import (
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

    @pytest.mark.parametrize("value", [1, 128, 255])
    def test_models_brightness_accepts_in_range(self, value: int) -> None:
        """Brightness within 1-255 is accepted.

        Technique: Boundary Value Analysis — lower/mid/upper bounds.
        """
        cmd = BulbSetCommand.model_validate({"brightness": value})
        assert cmd.brightness == value

    @pytest.mark.parametrize("value", [0, 256, -1])
    def test_models_brightness_rejects_out_of_range(self, value: int) -> None:
        """Brightness outside 1-255 is rejected.

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


class TestHaDiscoveryMetadata:
    """Both payload models carry ``ha_entities`` metadata the discovery
    generator (and ``app.discovery()``) turn into per-bulb HA entities.
    """

    def test_models_state_model_declares_light_sensor_number(self) -> None:
        """The state payload spans a light plus a power sensor and speed number.

        Technique: Specification-based — the three per-bulb components the
        state topic feeds .
        """
        components = [e["component"] for e in _ha_entities(BulbStateModel)]
        assert components == ["light", "sensor", "number"]

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
        prop = BulbStateModel.model_json_schema()["properties"][field]
        assert prop["x-cosalette-openhab"]["channel_type"] == expected_channel_type

    def test_models_on_off_commands_are_explicit_json_objects(self) -> None:
        """openHAB emits a channel's ``on``/``off`` verbatim, bypassing
        ``formatBeforePublish`` — so they must already be full JSON commands.

        Technique: Error Guessing — a bare ``ON`` string would reach the bulb
        unparsed; the metadata must carry ``{"state": "ON"}``.
        """
        brightness = BulbStateModel.model_json_schema()["properties"]["brightness"]
        params = brightness["x-cosalette-openhab"]["channel_params"]
        assert params["on"] == '{"state": "ON"}'
        assert params["off"] == '{"state": "OFF"}'

    def test_models_dimmer_min_matches_command_brightness_floor(self) -> None:
        """The openHAB dimmer ``min`` matches ``brightness`` ``ge=1``.

        A generated openHAB config must never be able to emit a brightness the
        ``/set`` validator would reject.

        Technique: Specification-based — metadata/validation consistency
        (PR #238 review finding).
        """
        for model in (BulbStateModel, BulbSetCommand):
            params = model.model_json_schema()["properties"]["brightness"][
                "x-cosalette-openhab"
            ]["channel_params"]
            assert params["min"] == 1


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
