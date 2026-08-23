"""Hardware adapter port for wiz2mqtt.

Defines the Protocol class for the WiZ bulb interface, following the
Ports & Adapters (Hexagonal Architecture) pattern. Production code depends
only on this protocol — concrete adapters are injected at runtime by
cosalette's adapter registry.
"""

from __future__ import annotations

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

        Prefers the push-populated cache; falls back to a live poll when
        no push has been received recently (empirical push-health check).
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
    ) -> None:
        """Apply a partial state update to the bulb.

        Colour temperature is clamped to the bulb's real Kelvin range and
        scene ids are validated against the bulb's class before sending.
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
