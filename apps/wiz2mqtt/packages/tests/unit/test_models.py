"""Unit tests for models.py — payload validation + discovery metadata (cap-10u.12,
cap-10u.14).

Test Techniques Used:
- Equivalence Partitioning: valid single-field, multi-field, and empty payloads
- Boundary Value Analysis: brightness 1-255, color channels 0-255, effect_speed 10-200
- Decision Table: color/color_temp/effect/hsb mutual exclusion combinations
- Error Guessing: extra/unknown fields, out-of-range values
- Specification-based: the HA ``ha_entities`` discovery metadata each model carries
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wiz2mqtt.models import WIZ_EFFECT_LIST, BulbSetCommand, BulbStateModel

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

    def test_models_effect_accepts_minimum_value(self) -> None:
        """effect=1 is the minimum valid scene ID.

        Technique: Boundary Value Analysis — lower bound (ge=1).
        """
        cmd = BulbSetCommand.model_validate({"effect": 1})
        assert cmd.effect == 1

    def test_models_effect_accepts_maximum_value(self) -> None:
        """effect=1000 is the pywizlight scene ceiling, must be accepted.

        Technique: Boundary Value Analysis — upper bound (le=1000).
        """
        cmd = BulbSetCommand.model_validate({"effect": 1000})
        assert cmd.effect == 1000

    def test_models_effect_rejects_zero(self) -> None:
        """effect=0 is invalid (scene IDs start at 1).

        Technique: Boundary Value Analysis — just below lower bound.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect": 0})

    def test_models_effect_rejects_above_maximum(self) -> None:
        """effect above 1000 is rejected.

        Technique: Boundary Value Analysis — just outside upper bound.
        """
        with pytest.raises(ValidationError):
            BulbSetCommand.model_validate({"effect": 1001})

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
        cmd = BulbSetCommand.model_validate({"effect": 7})
        assert cmd.effect == 7

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
            {"color": {"r": 1, "g": 2, "b": 3}, "effect": 7},
            {"color_temp": 3000, "effect": 7},
            {"color": {"r": 1, "g": 2, "b": 3}, "hsb": "1,2,3"},
            {"color_temp": 3000, "hsb": "1,2,3"},
            {"effect": 7, "hsb": "1,2,3"},
            {"color": {"r": 1, "g": 2, "b": 3}, "color_temp": 3000, "effect": 7},
            {
                "color": {"r": 1, "g": 2, "b": 3},
                "color_temp": 3000,
                "effect": 7,
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
# Home Assistant discovery metadata (cap-10u.14)
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
        state topic feeds (cap-10u.14).
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
