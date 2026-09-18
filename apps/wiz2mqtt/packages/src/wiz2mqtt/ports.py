"""Hardware adapter port for wiz2mqtt.

Defines the Protocol class for the WiZ bulb interface, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code depends
only on this protocol — concrete adapters are injected at runtime by
cosalette's adapter registry.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

from cosalette import HealthCheckable

if TYPE_CHECKING:
    from wiz2mqtt.models import BulbCapabilities, BulbState


@runtime_checkable
class WizBulbPort(HealthCheckable, Protocol):
    """Port for reading and writing WiZ bulb state.

    Bulbs are identified by IP address per call — there is no fixed
    inventory baked into the port itself, so it does not depend on the
    bulb inventory settings. Capabilities are auto-detected at first
    contact and never declared in config.

    Mutual exclusion between colour/colour-temperature/scene fields in a
    single ``set_state`` call is *not* enforced here — that is command
    handling's responsibility. This port passes through whatever
    combination it is given.
    """

    async def get_capabilities(self, ip: str) -> BulbCapabilities:
        """Return the bulb's auto-detected capabilities.

        Triggers first contact (connection + capability detection) if
        this is the first call for ``ip``.
        """
        ...

    async def get_state(self, ip: str) -> BulbState:
        """Return the bulb's current state.

        Prefers the cache populated from a push or pywizlight's cached parser.
        Freshness includes every syncPilot heartbeat pywizlight receives, even
        an unchanged packet it suppresses before invoking the adapter callback.
        Falls back to a live poll only after that heartbeat clock is stale.
        """
        ...

    def invalidate_cache(self, ip: str) -> None:
        """Discard any cached state for *ip*, forcing the next ``get_state``
        to perform an authoritative read.

        Called by the return-path's write-and-verify loop so each
        read-back reflects the bulb's real state, not the optimistic merge
        ``set_state`` applied (ADR-008 review fix).
        """
        ...

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
        speed: int | None = None,
    ) -> None:
        """Apply a partial state update to the bulb.

        Colour temperature is clamped to the bulb's real Kelvin range and
        scene ids are validated against the bulb's class before sending.
        ``speed`` is the colour-cycling effect speed (pywizlight accepts
        ``10..200``).
        """
        ...

    def set_unreachable(self, ip: str, unreachable: bool) -> None:
        """Force *ip* to behave as unreachable (ADR-008 test support).

        While set, ``get_state`` and ``set_state`` raise
        :class:`~wiz2mqtt.errors.WizTimeoutError` for ``ip``. Production use
        is chaos-testing a specific bulb; every unit test drives this
        through :class:`~wiz2mqtt.adapters.fake.FakeWizBulbAdapter`.
        """
        ...

    def boot(self, ip: str, default_state: BulbState) -> None:
        """Simulate *ip* booting into *default_state* (ADR-008).

        Clears any :meth:`set_unreachable` flag, replaces the cached state
        with *default_state*, and fires the callback registered via
        :meth:`register_boot_callback` with ``ip`` — standing in for
        pywizlight's firstBeat notification, which the production adapter
        routes through the same callback (cap-bjw9.4).
        """
        ...

    def register_boot_callback(self, callback: Callable[[str], None]) -> None:
        """Register *callback* to be invoked with a bulb's ip on boot.

        The production adapter invokes it on a pywizlight firstBeat for a
        configured ip (cap-bjw9.4); an unconfigured ip is ignored.
        """
        ...

    def refuse_writes(self, ip: str, count: int) -> None:
        """Make the next *count* ``set_state`` calls for *ip* no-ops.

        Each of the next *count* calls succeeds (raises nothing) but leaves
        the cached/reported state unchanged, so a subsequent ``get_state``
        still reads the old value — the three-retry rule's test support.
        """
        ...

    async def __aenter__(self) -> Self:
        """Enter async context: no-op — connections are lazy per bulb.

        Enables cosalette adapter lifecycle management via
        ``AsyncExitStack``.
        """
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context: close every connection opened so far."""
        ...
