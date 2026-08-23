"""Unit tests for commands.py — set-command to WizBulbPort.set_state translation.

Test Techniques Used:
- Equivalence Partitioning: ON/OFF/absent state; color present/absent
- Specification-based: field-by-field mapping onto set_state's kwarg names
- Round-trip Testing: RGB in -> hue/saturation out via the colour module
"""

from __future__ import annotations

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
        """effect maps onto the scene kwarg (WiZ scene ids are integers).

        Technique: Specification-based — direct field mapping.
        """
        kwargs = to_set_state_kwargs(BulbSetCommand.model_validate({"effect": 7}))
        assert kwargs["scene"] == 7


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
