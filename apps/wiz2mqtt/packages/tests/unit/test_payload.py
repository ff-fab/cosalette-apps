"""Unit tests for payload.py — retained state payload construction (cap-10u.13).

Test Techniques Used:
- Specification-based: HA's schema:json shape plus the openHAB hsb key
- Decision Table: color_mode selection (cct / rgb / plain on-off)
- Equivalence Partitioning: optional-field presence per known/unknown value
- Boundary Value Analysis: hsb dimming-percent rounding at brightness extremes
"""

from __future__ import annotations

import dataclasses

from wiz2mqtt.models import BulbState
from wiz2mqtt.payload import build_state_payload

_EMPTY = BulbState(
    state=None,
    brightness=None,
    hue=None,
    saturation=None,
    color_temp_kelvin=None,
    scene=None,
)


def _state(**overrides: object) -> BulbState:
    return dataclasses.replace(_EMPTY, **overrides)


class TestMandatoryState:
    """``state`` is mandatory in every payload — HA discards on KeyError."""

    def test_payload_on_state_reports_on(self) -> None:
        """Technique: Specification-based — bulb on maps to the literal 'ON'."""
        payload = build_state_payload(_state(state=True))
        assert payload["state"] == "ON"

    def test_payload_off_state_reports_off(self) -> None:
        """Technique: Specification-based — bulb off maps to the literal 'OFF'."""
        payload = build_state_payload(_state(state=False))
        assert payload["state"] == "OFF"

    def test_payload_unknown_state_reports_off(self) -> None:
        """A never-polled bulb (``state=None``) still reports a valid payload.

        Technique: Boundary Value Analysis — the unset/None case must not
        omit the mandatory key.
        """
        payload = build_state_payload(_state(state=None))
        assert payload["state"] == "OFF"


class TestOptionalFields:
    """brightness/effect/effect_speed/power_draw_w are omitted when unknown."""

    def test_payload_omits_brightness_when_unknown(self) -> None:
        """Technique: Equivalence Partitioning — unknown-value branch."""
        payload = build_state_payload(_state(state=True))
        assert "brightness" not in payload

    def test_payload_includes_brightness_when_known(self) -> None:
        """Technique: Equivalence Partitioning — known-value branch."""
        payload = build_state_payload(_state(state=True, brightness=200))
        assert payload["brightness"] == 200

    def test_payload_includes_effect_from_scene(self) -> None:
        """``effect`` is HA's key for what the domain model calls ``scene``.

        Technique: Specification-based — field renaming at the wire boundary.
        """
        payload = build_state_payload(_state(state=True, scene=7))
        assert payload["effect"] == 7

    def test_payload_omits_effect_speed_and_power_when_unknown(self) -> None:
        """Technique: Equivalence Partitioning — unknown-value branch."""
        payload = build_state_payload(_state(state=True))
        assert "effect_speed" not in payload
        assert "power_draw_w" not in payload

    def test_payload_includes_effect_speed_and_power_when_known(self) -> None:
        """Technique: Equivalence Partitioning — known-value branch."""
        payload = build_state_payload(
            _state(state=True, effect_speed=150, power_draw_w=8.44)
        )
        assert payload["effect_speed"] == 150
        assert payload["power_draw_w"] == 8.4  # rounded to 1 decimal


class TestColorMode:
    """color_mode/color/color_temp/hsb are gated on the bulb's actual mode."""

    def test_payload_plain_on_off_has_no_color_keys(self) -> None:
        """Neither colour nor colour-temp known: no color_mode at all.

        Technique: Decision Table — neither CCT nor RGB branch.
        """
        payload = build_state_payload(_state(state=True, brightness=100))
        assert "color_mode" not in payload
        assert "color" not in payload
        assert "color_temp" not in payload
        assert "hsb" not in payload

    def test_payload_cct_mode_reports_color_temp(self) -> None:
        """Technique: Decision Table — CCT branch (color_temp_kelvin > 0)."""
        payload = build_state_payload(_state(state=True, color_temp_kelvin=4000))
        assert payload["color_mode"] == "color_temp"
        assert payload["color_temp"] == 4000
        assert payload["color_temp_kelvin"] is True

    def test_payload_cct_mode_has_no_rgb_keys(self) -> None:
        """Technique: Decision Table — CCT branch excludes the RGB keys."""
        payload = build_state_payload(_state(state=True, color_temp_kelvin=4000))
        assert "color" not in payload
        assert "hsb" not in payload

    def test_payload_rgb_mode_reports_color_and_hsb(self) -> None:
        """Technique: Round-trip Testing — known hue/saturation/brightness.

        Pure red at full brightness: hue=0, saturation=100 -> RGB (255,0,0).
        """
        payload = build_state_payload(
            _state(state=True, hue=0.0, saturation=100.0, brightness=255)
        )
        assert payload["color_mode"] == "rgb"
        assert payload["color"] == {"r": 255, "g": 0, "b": 0}
        assert payload["hsb"] == "0,100,100"

    def test_payload_rgb_mode_hsb_uses_dimming_percent_not_0_255(self) -> None:
        """hsb's third field is a 0-100 dimming percent (openHAB), not 0-255.

        Technique: Boundary Value Analysis — half brightness rounds to 50%.
        """
        payload = build_state_payload(
            _state(state=True, hue=120.0, saturation=50.0, brightness=128)
        )
        assert payload["hsb"] == "120,50,50"

    def test_payload_rgb_mode_defaults_brightness_to_full_when_unknown(self) -> None:
        """A colour reading with no brightness assumes full brightness for RGB.

        Technique: Boundary Value Analysis — brightness=None edge case.
        """
        payload = build_state_payload(_state(state=True, hue=0.0, saturation=100.0))
        assert payload["color"] == {"r": 255, "g": 0, "b": 0}
        assert payload["hsb"] == "0,100,100"

    def test_payload_colortemp_takes_priority_over_stale_rgb_residue(self) -> None:
        """A non-zero color_temp_kelvin always wins over hue/saturation.

        pywizlight can report stale RGB residue alongside a valid colortemp
        (see wiz2mqtt.colour.is_cct_mode) — the payload must not leak it.

        Technique: Decision Table — both colortemp and hue/saturation set.
        """
        payload = build_state_payload(
            _state(state=True, color_temp_kelvin=4000, hue=0.0, saturation=100.0)
        )
        assert payload["color_mode"] == "color_temp"
        assert "color" not in payload
        assert "hsb" not in payload

    def test_payload_rgb_mode_hsb_wraps_hue_at_boundary(self) -> None:
        """hue ≥ 359.5 must not produce \"360\" — clamp via % 360.

        Technique: Boundary Value Analysis — the exact rounding boundary.
        """
        payload = build_state_payload(
            _state(state=True, hue=359.5, saturation=100.0, brightness=255)
        )
        hue_str = payload["hsb"].split(",")[0]  # type: ignore[union-attr]
        assert int(hue_str) < 360, f"hue '{hue_str}' is out of range [0, 359]"

    def test_payload_rgb_mode_omits_color_when_only_hue_known(self) -> None:
        """saturation=None: neither hue nor saturation alone triggers RGB mode.

        Technique: Equivalence Partitioning — one-None partition (hue set, sat absent).
        """
        payload = build_state_payload(_state(state=True, hue=0.0, saturation=None))
        assert "color_mode" not in payload

    def test_payload_rgb_mode_omits_color_when_only_saturation_known(self) -> None:
        """hue=None: neither hue nor saturation alone triggers RGB mode.

        Technique: Equivalence Partitioning — one-None partition (sat set, hue absent).
        """
        payload = build_state_payload(_state(state=True, hue=None, saturation=100.0))
        assert "color_mode" not in payload
