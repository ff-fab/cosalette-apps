"""In-memory adapter for ``--dry-run`` mode and testing.

No ``pywizlight`` import at all — state and capabilities live in plain
dicts, seeded with sensible defaults so tests don't need boilerplate setup
unless they care about specific values.

Mirrors the production adapter's push→wake path: :meth:`inject_push`
stands in for a real UDP notification and arms the same telemetry
trigger, so ``--dry-run`` and the integration suite exercise
event-driven publication rather than falling back to the heartbeat.
"""

from __future__ import annotations

from types import TracebackType
from typing import Annotated, Self

from cosalette import EntityNotifier, Optional

from wiz2mqtt.errors import WizTimeoutError
from wiz2mqtt.models import BulbCapabilities, BulbState
from wiz2mqtt.settings import Wiz2MqttSettings

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

    def __init__(
        self,
        # Both are Optional() so a bare ``FakeWizBulbAdapter()`` still works
        # in unit tests that never touch the push path.  Under the framework
        # (``--dry-run``) both providers exist and are always injected.
        settings: Annotated[Wiz2MqttSettings | None, Optional()] = None,
        notify: Annotated[EntityNotifier | None, Optional()] = None,
    ) -> None:
        self._notify = notify
        self._name_by_ip = (
            {bulb.ip: bulb.name for bulb in settings.bulbs}
            if settings is not None
            else {}
        )
        self._capabilities: dict[str, BulbCapabilities] = {}
        self._state: dict[str, BulbState] = {}
        self._fail_next: dict[str, Exception] = {}
        self.always_fail: bool = (
            False  # when True, every get_state raises WizTimeoutError
        )
        self.get_state_call_count: int = 0  # total get_state invocations

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
        self.get_state_call_count += 1
        if self.always_fail:
            raise WizTimeoutError(f"always_fail is set for {ip}")
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

    def bind(self, settings: Wiz2MqttSettings, notify: EntityNotifier) -> None:
        """Hand a pre-built fake the two dependencies DI would have injected.

        Integration harnesses build the fake before the ``App`` exists so
        tests can prime it, then register it via a closure — which bypasses
        constructor injection.  This restores it.
        """
        self._notify = notify
        self._name_by_ip = {bulb.ip: bulb.name for bulb in settings.bulbs}

    def inject_push(self, ip: str, state: BulbState) -> None:
        """Simulate a push arriving: overwrite the cache, then arm the entity.

        The arm is skipped for an unbound fake or an IP outside
        ``settings.bulbs`` — same no-op rule as the production ``_wake``.
        """
        self._state[ip] = state
        name = self._name_by_ip.get(ip)
        if self._notify is not None and name is not None:
            self._notify(name)

    def fail_next(self, ip: str, exc: Exception) -> None:
        """Raise *exc* on the next call for *ip*, then clear."""
        self._fail_next[ip] = exc
