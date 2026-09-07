"""Unit tests for commands.py — set-command to WizBulbPort.set_state translation.

Test Techniques Used:
- Equivalence Partitioning: ON/OFF/absent state; color/hsb present/absent
- Specification-based: field-by-field mapping onto set_state's kwarg names
- Round-trip Testing: RGB in -> hue/saturation out via the colour module
- Decision Table: hsb brightness only fills in when brightness is absent
"""

from __future__ import annotations

import pytest

from wiz2mqtt.colour import hue_saturation_to_rgb
from wiz2mqtt.commands import to_set_state_kwargs
from wiz2mqtt.models import BulbSetCommand

# ---------------------------------------------------------------------------
# state mapping
# ---------------------------------------------------------------------------


class TestStateMapping:
    """HA's "ON"/"OFF" strings map to Python bool for the port."""

    def test_commands_state_on_maps_to_true(self) -> None:
        """ "ON" becomes True.

        Technique: Equivalence Partitioning — state=ON.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"state": "ON"}))
        assert kwargs["state"] is True

    def test_commands_state_off_maps_to_false(self) -> None:
        """ "OFF" becomes False.

        Technique: Equivalence Partitioning — state=OFF.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"state": "OFF"}))
        assert kwargs["state"] is False

    def test_commands_absent_state_maps_to_none(self) -> None:
        """No state field in the payload stays None (partial-update passthrough).

        Technique: Equivalence Partitioning — state absent.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"brightness": 100}))
        assert kwargs["state"] is None


# ---------------------------------------------------------------------------
# direct passthrough fields
# ---------------------------------------------------------------------------


class TestPassthroughFields:
    """brightness, color_temp and effect map 1:1 onto set_state's kwargs."""

    def test_commands_brightness_passes_through(self) -> None:
        """brightness maps unchanged onto the brightness kwarg.

        Technique: Specification-based — direct field mapping.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"brightness": 200}))
        assert kwargs["brightness"] == 200

    def test_commands_color_temp_maps_to_color_temp_kelvin(self) -> None:
        """color_temp maps onto the color_temp_kelvin kwarg.

        Technique: Specification-based — HA's color_temp is Kelvin per the
        color_temp_kelvin:true wire contract.
        """
        cmd = BulbSetCommand.model_validate({"color_temp": 4000})
        kwargs = to_set_state_kwargs(cmd)
        assert kwargs["color_temp_kelvin"] == 4000

    def test_commands_effect_maps_to_scene(self) -> None:
        """effect (a scene *name*) maps onto the numeric scene kwarg.

        Technique: Specification-based — name-to-id translation at the boundary.
        """
        cmd = BulbSetCommand.model_validate({"effect": "Forest"})
        assert to_set_state_kwargs(cmd)["scene"] == 7  # pywizlight SCENES["Forest"]

    def test_commands_effect_speed_maps_to_speed(self) -> None:
        """effect_speed maps onto the speed kwarg pywizlight's PilotBuilder wants.

        Technique: Specification-based — direct field mapping.
        """
        cmd = BulbSetCommand.model_validate({"effect_speed": 90})
        assert to_set_state_kwargs(cmd)["speed"] == 90

    def test_commands_absent_effect_speed_maps_to_none(self) -> None:
        """No effect_speed field stays None (partial-update passthrough).

        Technique: Equivalence Partitioning — effect_speed absent.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"state": "ON"}))
        assert kwargs["speed"] is None


# ---------------------------------------------------------------------------
# color -> hue/saturation conversion
# ---------------------------------------------------------------------------


class TestColorConversion:
    """color.{r,g,b} converts to canonical hue/saturation, never passed as RGB."""

    def test_commands_no_color_leaves_hue_saturation_none(self) -> None:
        """No color field in the payload leaves hue/saturation unset.

        Technique: Equivalence Partitioning — color absent.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"brightness": 50}))
        assert kwargs["hue"] is None
        assert kwargs["saturation"] is None

    def test_commands_color_converts_to_hue_saturation(self) -> None:
        """A given color is converted to (hue, saturation), never left as RGB.

        Technique: Specification-based — verifies hue/saturation are populated,
        no raw RGB key leaks through, and round-trip reconstructs pure red exactly
        (pure-saturated primaries are lossless through the hsv conversion).
        """
        cmd = BulbSetCommand.model_validate({"color": {"r": 255, "g": 0, "b": 0}})
        kwargs = to_set_state_kwargs(cmd)

        assert kwargs["hue"] is not None
        assert kwargs["saturation"] is not None
        assert "color" not in kwargs

        reconstructed = hue_saturation_to_rgb(
            kwargs["hue"], kwargs["saturation"], brightness=255
        )
        assert reconstructed == (255, 0, 0)


# ---------------------------------------------------------------------------
# hsb -> hue/saturation/brightness conversion (openHAB Color channel)
# ---------------------------------------------------------------------------


class TestHsbConversion:
    """openHAB's ``"h,s,b"`` Color string converts to canonical hue/saturation,
    contributing its brightness percent only when no explicit brightness is set.
    """

    def test_commands_hsb_converts_to_hue_saturation_brightness(self) -> None:
        """A bare hsb payload populates hue, saturation and brightness.

        Technique: Specification-based — the openHAB Color wire form maps onto
        three separate set_state kwargs.
        """
        kwargs = to_set_state_kwargs(
            BulbSetCommand.model_validate({"hsb": "120,100,100"})
        )
        assert kwargs["hue"] == pytest.approx(120.0)
        assert kwargs["saturation"] == pytest.approx(100.0)
        assert kwargs["brightness"] == 255
        assert "hsb" not in kwargs

    def test_commands_explicit_brightness_wins_over_hsb_brightness(self) -> None:
        """An explicit ``brightness`` field is not overwritten by hsb's percent.

        Technique: Decision Table — brightness present vs absent alongside hsb.
        """
        kwargs = to_set_state_kwargs(
            BulbSetCommand.model_validate({"hsb": "120,100,100", "brightness": 10})
        )
        assert kwargs["brightness"] == 10

    def test_commands_no_hsb_leaves_hue_saturation_none(self) -> None:
        """No hsb (and no color) leaves hue/saturation unset.

        Technique: Equivalence Partitioning — hsb absent.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"state": "ON"}))
        assert kwargs["hue"] is None
        assert kwargs["saturation"] is None
