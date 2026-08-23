"""Pure colour/capability helpers — zero cosalette or pywizlight imports.

``pywizlight``'s ``PilotBuilder(hucolor=...)`` expects ``(hue, saturation)``
with hue in ``0..360`` and saturation in ``0..100`` (see
``pywizlight.rgbcw.hs2rgbcw``) — *not* the ``0..1`` saturation
``colorsys.rgb_to_hsv`` returns. All hue/saturation values in this module
use pywizlight's own ``0..360`` / ``0..100`` convention so no rescaling is
needed at the adapter boundary.
"""

from __future__ import annotations

import colorsys
from typing import TYPE_CHECKING

from wiz2mqtt.errors import WizUnsupportedCommandError

if TYPE_CHECKING:
    from wiz2mqtt.models import BulbCapabilities


def clamp_kelvin(value: int, caps: BulbCapabilities) -> int:
    """Clamp *value* to the bulb's real Kelvin range.

    ``pywizlight`` does not validate ``colortemp`` — it silently clamps to
    a hardcoded 1000-10000 range regardless of what the bulb actually
    supports. Clamp to the bulb's own ``kelvin_min``/``kelvin_max`` first.
    Bulbs with no detected range (``color_tmp`` unsupported) pass through
    unchanged and rely on pywizlight's own fallback clamp.
    """
    if caps.kelvin_min is None or caps.kelvin_max is None:
        return value
    return max(caps.kelvin_min, min(value, caps.kelvin_max))


def validate_scene(scene_id: int, caps: BulbCapabilities) -> None:
    """Raise if *scene_id* isn't supported by the bulb's class.

    Setting a class-unsupported scene can make a bulb unavailable — a
    latent bricking bug in the legacy control script. Validated locally so
    an unsupported id is never sent to the bulb at all.
    """
    from pywizlight.bulblibrary import (
        BulbClass,  # noqa: PLC0415 — lazy import by design
    )
    from pywizlight.scenes import (  # noqa: PLC0415 — lazy import by design
        SCENES,
        SCENES_BY_CLASS,
    )

    # SCENES_BY_CLASS is keyed by scene *name*, not id — translate first.
    scene_name = SCENES.get(scene_id)
    try:
        bulb_class = BulbClass[caps.bulb_class]
    except KeyError:
        msg = f"Unknown bulb class {caps.bulb_class!r}"
        raise WizUnsupportedCommandError(msg) from None
    allowed_names = SCENES_BY_CLASS.get(bulb_class, [])
    if scene_name is None or scene_name not in allowed_names:
        msg = f"Scene {scene_id} is not supported by bulb class {caps.bulb_class}"
        raise WizUnsupportedCommandError(msg)


def rgb_to_hue_saturation(
    r: float, g: float, b: float, cold_white: float = 0
) -> tuple[float, float]:
    """Convert an 0-255 RGB triple plus cold-white channel to (hue, saturation).

    Uses ``pywizlight``'s own ``rgbcw2hs`` — *not* ``colorsys.rgb_to_hsv``.
    The wire splits colour between the RGB channels and a separate
    cold-white ("c") channel: a pastel colour is represented as a
    saturated RGB vector *plus* cw, not as desaturated RGB. Ignoring
    ``cold_white`` (as plain ``colorsys`` conversion does) silently
    reports full saturation for any colour mixed with white light.
    ``cold_white`` defaults to 0 for callers with no white channel to
    report (e.g. pure-RGB test fixtures).
    """
    from pywizlight.rgbcw import rgbcw2hs  # noqa: PLC0415 — lazy import by design

    return rgbcw2hs((r, g, b), cold_white)


def hue_saturation_to_rgb(
    hue: float, saturation: float, brightness: int
) -> tuple[int, int, int]:
    """Reconstruct a display RGB triple from canonical (hue, saturation, brightness).

    Uses standard HSV->RGB (``colorsys``), *not* ``pywizlight``'s own
    ``get_rgb()`` wire readback or ``hs2rgbcw`` wire encoding — that wire
    projection discards luminance (e.g. ``(200, 200, 255)`` round-trips
    through the wire as ``(0, 0, 109)`` with ``w=128``, and every grey and
    white collapses to an identical ``(0, 0, 0)`` with ``w=128``).
    ``brightness`` is 0-255, matching :func:`BulbState.brightness`.
    """
    r, g, b = colorsys.hsv_to_rgb(hue / 360, saturation / 100, brightness / 255)
    return round(r * 255), round(g * 255), round(b * 255)


def is_cct_mode(color_temp_kelvin: int | None) -> bool:
    """True when the bulb is in CCT (colour-temperature) mode.

    Must be checked *before* trusting a populated ``get_rgb()`` readback:
    ``pywizlight``'s parser can return both a non-zero ``get_colortemp()``
    and a fully-populated RGB tuple at once — stale RGB residue from a
    prior colour-mode session — so ``get_colortemp() != 0`` is the only
    reliable mode signal, never ``get_rgb()``.
    """
    return bool(color_temp_kelvin)
