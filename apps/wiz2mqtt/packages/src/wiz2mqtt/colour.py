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
    bulb_class = BulbClass[caps.bulb_class]
    allowed_names = SCENES_BY_CLASS.get(bulb_class, [])
    if scene_name is None or scene_name not in allowed_names:
        msg = f"Scene {scene_id} is not supported by bulb class {caps.bulb_class}"
        raise WizUnsupportedCommandError(msg)


def rgb_to_hue_saturation(r: float, g: float, b: float) -> tuple[float, float]:
    """Convert an 0-255 RGB triple to (hue in 0-360, saturation in 0-100).

    ``pywizlight``'s state readback has no hue/saturation getter, only
    ``get_rgb()`` — this reconstructs the canonical (hue, saturation)
    pair for state reads, discarding value/brightness (read separately
    via ``get_brightness()``).
    """
    hue, saturation, _value = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    return hue * 360, saturation * 100
