"""Unit tests for models.py — BulbSetCommand payload validation (cap-10u.12).

Test Techniques Used:
- Equivalence Partitioning: valid single-field, multi-field, and empty payloads
- Boundary Value Analysis: brightness 1-255, color channels 0-255
- Decision Table: color/color_temp/effect mutual exclusion combinations
- Error Guessing: extra/unknown fields, out-of-range values
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wiz2mqtt.models import BulbSetCommand

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


# ---------------------------------------------------------------------------
# Mutual exclusion — color / color_temp / effect
# ---------------------------------------------------------------------------


class TestMutualExclusion:
    """color, color_temp and effect must never co-occur in one payload."""

    def test_models_color_alone_is_valid(self) -> None:
        """color with no color_temp/effect is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"color": {"r": 1, "g": 2, "b": 3}})
        assert cmd.color is not None

    def test_models_color_temp_alone_is_valid(self) -> None:
        """color_temp with no color/effect is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"color_temp": 3000})
        assert cmd.color_temp == 3000

    def test_models_effect_alone_is_valid(self) -> None:
        """effect with no color/color_temp is a valid payload.

        Technique: Decision Table — single field set, others None.
        """
        cmd = BulbSetCommand.model_validate({"effect": 7})
        assert cmd.effect == 7

    @pytest.mark.parametrize(
        "payload",
        [
            {"color": {"r": 1, "g": 2, "b": 3}, "color_temp": 3000},
            {"color": {"r": 1, "g": 2, "b": 3}, "effect": 7},
            {"color_temp": 3000, "effect": 7},
            {"color": {"r": 1, "g": 2, "b": 3}, "color_temp": 3000, "effect": 7},
        ],
        ids=["color+color_temp", "color+effect", "color_temp+effect", "all_three"],
    )
    def test_models_rejects_conflicting_combinations(
        self, payload: dict[str, object]
    ) -> None:
        """Any two-or-more-way overlap between the three fields is rejected.

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
