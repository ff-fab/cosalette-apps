"""In-memory adapter for ``--dry-run`` mode and testing.

No ``pywizlight`` import at all — state and capabilities live in plain
dicts, seeded with sensible defaults so tests don't need boilerplate setup
unless they care about specific values.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from wiz2mqtt.models import BulbCapabilities, BulbState

_DEFAULT_CAPABILITIES = BulbCapabilities(
    bulb_class="RGB",
    color=True,
    color_tmp=True,
    effect=True,
    brightness=True,
    kelvin_min=2200,
    kelvin_max=6500,
)

_DEFAULT_STATE = BulbState(
    state=False,
    brightness=None,
    hue=None,
    saturation=None,
    color_temp_kelvin=None,
    scene=None,
    effect_speed=None,
    power_draw_w=None,
)


class FakeWizBulbAdapter:
    """Fake adapter satisfying :class:`wiz2mqtt.ports.WizBulbPort` structurally."""

    def __init__(self) -> None:
        self._capabilities: dict[str, BulbCapabilities] = {}
        self._state: dict[str, BulbState] = {}
        self._fail_next: dict[str, Exception] = {}

    def _raise_if_primed(self, ip: str) -> None:
        exc = self._fail_next.pop(ip, None)
        if exc is not None:
            raise exc

    async def get_capabilities(self, ip: str) -> BulbCapabilities:
        """Return the bulb's capabilities, defaulting to a full-featured RGB bulb."""
        self._raise_if_primed(ip)
        return self._capabilities.setdefault(ip, _DEFAULT_CAPABILITIES)

    async def get_state(self, ip: str) -> BulbState:
        """Return the bulb's current state, defaulting to off/unset."""
        self._raise_if_primed(ip)
        return self._state.setdefault(ip, _DEFAULT_STATE)

    async def set_state(
        self,
        ip: str,
        *,
        state: bool | None = None,
        brightness: int | None = None,
        hue: float | None = None,
        saturation: float | None = None,
        color_temp_kelvin: int | None = None,
        scene: int | None = None,
    ) -> None:
        """Merge the given fields into the bulb's stored state."""
        self._raise_if_primed(ip)
        current = self._state.setdefault(ip, _DEFAULT_STATE)
        self._state[ip] = current.replace_non_none(
            state=state,
            brightness=brightness,
            hue=hue,
            saturation=saturation,
            color_temp_kelvin=color_temp_kelvin,
            scene=scene,
        )

    async def health_check(self) -> bool:
        """Always healthy — the fake has no connection to break."""
        return True

    async def __aenter__(self) -> Self:
        """Enter async context: no-op."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: no-op."""

    # -- Test helpers --------------------------------------------------------

    def inject_capabilities(self, ip: str, caps: BulbCapabilities) -> None:
        """Seed the capabilities a subsequent :meth:`get_capabilities` returns."""
        self._capabilities[ip] = caps

    def inject_push(self, ip: str, state: BulbState) -> None:
        """Simulate a push arriving, overwriting the cached state directly."""
        self._state[ip] = state

    def fail_next(self, ip: str, exc: Exception) -> None:
        """Raise *exc* on the next call for *ip*, then clear."""
        self._fail_next[ip] = exc
