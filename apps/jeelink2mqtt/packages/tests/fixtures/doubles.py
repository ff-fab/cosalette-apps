"""Shared test doubles for jeelink2mqtt tests.

Provides reusable fakes and stubs that mirror cosalette interfaces,
centralising the definition so changes to the framework API only
need updating in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeDeviceContext:
    """Minimal fake for ``cosalette.DeviceContext``.

    Captures publish calls in :attr:`published` and exposes a
    controllable :attr:`shutdown_requested` flag for receiver-loop tests.
    """

    published: list[tuple[str, str, bool]] = field(default_factory=list)
    _shutdown: bool = False

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        """Record a publish call as ``(topic, payload, retain)``."""
        self.published.append((topic, payload, retain))

    @property
    def shutdown_requested(self) -> bool:
        """Return the current shutdown flag value."""
        return self._shutdown
