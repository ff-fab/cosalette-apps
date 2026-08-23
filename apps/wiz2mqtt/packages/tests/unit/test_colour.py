"""Unit tests for colour.py — pure colour/capability helpers.

Test Techniques Used:
- Boundary Value Analysis: Kelvin clamping at min/max/mid
- Equivalence Partitioning: supported vs. unsupported scenes per bulb class
- Round-trip Testing: RGB <-> hue/saturation conversion sanity
- Error Guessing: unsupported scene raises, missing kelvin range passes through
- Decision Table: CCT-mode detection from colortemp value
"""

from __future__ import annotations

import pytest

from wiz2mqtt.colour import (
    clamp_kelvin,
    hue_saturation_to_rgb,
    is_cct_mode,
    rgb_to_hue_saturation,
    validate_scene,
)
from wiz2mqtt.errors import WizUnsupportedCommandError
from wiz2mqtt.models import BulbCapabilities

_RGB_CAPS = BulbCapabilities(
    bulb_class="RGB",
    color=True,
    color_tmp=True,
    effect=True,
    brightness=True,
    kelvin_min=2200,
    kelvin_max=6500,
)

_TW_CAPS = BulbCapabilities(
    bulb_class="TW",
    color=False,
    color_tmp=True,
    effect=True,
    brightness=True,
    kelvin_min=2700,
    kelvin_max=6500,
)

_SOCKET_CAPS = BulbCapabilities(
    bulb_class="SOCKET",
    color=False,
    color_tmp=False,
    effect=False,
    brightness=False,
    kelvin_min=None,
    kelvin_max=None,
)


# ---------------------------------------------------------------------------
# clamp_kelvin
# ---------------------------------------------------------------------------


class TestClampKelvin:
    """clamp_kelvin restricts values to the bulb's real Kelvin range."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (1000, 2200),  # below min -> boundary value analysis
            (2200, 2200),  # exactly min
            (4000, 4000),  # mid-range, unchanged
            (6500, 6500),  # exactly max
            (10000, 6500),  # above max -> boundary value analysis
        ],
    )
    def test_colour_clamp_kelvin_within_bulb_range(
        self, value: int, expected: int
    ) -> None:
        """Values outside the bulb's own range are clamped to it.

        Technique: Boundary Value Analysis — min/max/below/above/mid.
        """
        assert clamp_kelvin(value, _RGB_CAPS) == expected

    def test_colour_clamp_kelvin_passes_through_when_range_unknown(self) -> None:
        """Bulbs with no detected Kelvin range are left unclamped here.

        Technique: Error Guessing — pywizlight's own 1000-10000 fallback
        clamp still applies downstream.
        """
        assert clamp_kelvin(15000, _SOCKET_CAPS) == 15000


# ---------------------------------------------------------------------------
# validate_scene
# ---------------------------------------------------------------------------


class TestValidateScene:
    """validate_scene rejects scenes unsupported by the bulb's class."""

    def test_colour_validate_scene_accepts_supported_scene(self) -> None:
        """A scene id present in SCENES_BY_CLASS[RGB] does not raise.

        Technique: Equivalence Partitioning — supported-scene class.
        """
        validate_scene(1, _RGB_CAPS)  # "Ocean" — does not raise

    def test_colour_validate_scene_rejects_unsupported_scene(self) -> None:
        """A scene id absent from the TW bulb's allowed list raises.

        Technique: Equivalence Partitioning — unsupported-scene class.
        """
        with pytest.raises(WizUnsupportedCommandError):
            validate_scene(1, _TW_CAPS)  # "Ocean" is RGB-only

    def test_colour_validate_scene_rejects_for_class_with_no_scenes(self) -> None:
        """A bulb class absent from SCENES_BY_CLASS entirely rejects all scenes.

        Technique: Error Guessing — class with zero allowed scenes.
        """
        with pytest.raises(WizUnsupportedCommandError):
            validate_scene(1, _SOCKET_CAPS)

    def test_colour_validate_scene_raises_for_unknown_bulb_class(self) -> None:
        """validate_scene raises WizUnsupportedCommandError, not KeyError.

        Technique: Error Guessing — future/unknown class not in BulbClass enum.
        """
        unknown_caps = BulbCapabilities(
            bulb_class="COMPLETELY_UNKNOWN_CLASS",
            color=False,
            color_tmp=False,
            effect=False,
            brightness=False,
            kelvin_min=None,
            kelvin_max=None,
        )
        with pytest.raises(WizUnsupportedCommandError):
            validate_scene(1, unknown_caps)


# ---------------------------------------------------------------------------
# rgb_to_hue_saturation
# ---------------------------------------------------------------------------


class TestRgbToHueSaturation:
    """rgb_to_hue_saturation converts RGB + cold-white to pywizlight's hue/saturation.

    Cases use rgb=(0, 0, 0) + cold_white for "white" rather than
    rgb=(255, 255, 255) — a real bulb reports colour on the RGB channels
    and white on the separate cold-white channel, never both saturated at
    once; ``rgbcw2hs`` derives saturation from ``cold_white``, not from
    the RGB vector's own magnitude.
    """

    @pytest.mark.parametrize(
        ("rgb", "cold_white", "expected_hue", "expected_saturation"),
        [
            ((255, 0, 0), 0, 0.0, 100.0),  # pure red, no white channel
            ((0, 255, 0), 0, 120.0, 100.0),  # pure green, no white channel
            ((0, 0, 255), 0, 240.0, 100.0),  # pure blue, no white channel
            ((0, 0, 0), 255, 0.0, 0.0),  # full cold-white -> zero saturation
        ],
    )
    def test_colour_rgb_to_hue_saturation_primary_colours(
        self,
        rgb: tuple[int, int, int],
        cold_white: int,
        expected_hue: float,
        expected_saturation: float,
    ) -> None:
        """Primary colours map to their known hue/saturation values.

        Technique: Round-trip Testing — well-known RGB -> HSV fixed points.
        """
        hue, saturation = rgb_to_hue_saturation(*rgb, cold_white)
        assert hue == pytest.approx(expected_hue, abs=0.01)
        assert saturation == pytest.approx(expected_saturation, abs=0.01)

    def test_colour_rgb_to_hue_saturation_blends_cold_white_into_saturation(
        self,
    ) -> None:
        """A partial cold-white channel reduces saturation below fully-saturated red.

        Plain ``colorsys.rgb_to_hsv`` on the RGB channels alone would
        report 100% saturation here regardless — this is the exact defect
        the ``rgbcw2hs`` conversion fixes.

        Technique: Round-trip Testing — known rgbcw2hs fixed point.
        """
        hue, saturation = rgb_to_hue_saturation(255, 0, 0, cold_white=64)
        assert hue == pytest.approx(0.0, abs=0.01)
        assert saturation == pytest.approx(75.0, abs=0.01)

    def test_colour_rgb_to_hue_saturation_within_pywizlight_ranges(self) -> None:
        """Output stays within pywizlight's hucolor ranges: hue 0-360, saturation 0-100.

        Technique: Boundary Value Analysis — range containment, not just fixed points.
        """
        hue, saturation = rgb_to_hue_saturation(128, 64, 200)
        assert 0.0 <= hue < 360.0
        assert 0.0 <= saturation <= 100.0


# ---------------------------------------------------------------------------
# hue_saturation_to_rgb
# ---------------------------------------------------------------------------


class TestHueSaturationToRgb:
    """hue_saturation_to_rgb reconstructs display RGB via standard HSV->RGB."""

    @pytest.mark.parametrize(
        ("hue", "saturation", "brightness", "expected_rgb"),
        [
            (0.0, 100.0, 255, (255, 0, 0)),  # pure red at full brightness
            (120.0, 100.0, 255, (0, 255, 0)),  # pure green at full brightness
            (0.0, 0.0, 255, (255, 255, 255)),  # zero saturation -> grey/white
            (0.0, 100.0, 0, (0, 0, 0)),  # zero brightness -> black regardless of hue
        ],
    )
    def test_colour_hue_saturation_to_rgb_fixed_points(
        self,
        hue: float,
        saturation: float,
        brightness: int,
        expected_rgb: tuple[int, int, int],
    ) -> None:
        """Known HSV fixed points map to their expected RGB triples.

        Technique: Round-trip Testing — well-known HSV -> RGB fixed points.
        """
        assert hue_saturation_to_rgb(hue, saturation, brightness) == expected_rgb


# ---------------------------------------------------------------------------
# is_cct_mode
# ---------------------------------------------------------------------------


class TestIsCctMode:
    """is_cct_mode keys off colortemp alone, never rgb."""

    @pytest.mark.parametrize(
        ("color_temp_kelvin", "expected"),
        [
            (None, False),  # no colortemp reported -> colour mode
            (0, False),  # explicit zero -> colour mode
            (4000, True),  # non-zero colortemp -> CCT mode
        ],
    )
    def test_colour_is_cct_mode_keys_off_colortemp(
        self, color_temp_kelvin: int | None, expected: bool
    ) -> None:
        """Technique: Decision Table — colortemp value -> mode."""
        assert is_cct_mode(color_temp_kelvin) is expected
