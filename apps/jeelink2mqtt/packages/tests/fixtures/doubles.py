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
    published_state: list[dict[str, object]] = field(default_factory=list)
    availability_calls: list[str] = field(default_factory=list)
    """Sequence of ``"available"``/``"unavailable"`` markers, in call order."""

    _shutdown: bool = False

    async def publish(self, topic: str, payload: str, *, retain: bool = False) -> None:
        """Record a publish call as ``(topic, payload, retain)``."""
        self.published.append((topic, payload, retain))

    async def publish_state(
        self, payload: dict[str, object], *, retain: bool = True
    ) -> None:  # noqa: ARG002 — retain unused, mirrors DeviceContext signature
        """Record a publish_state call."""
        self.published_state.append(payload)

    async def mark_unavailable(self) -> None:
        """Record an unavailable marker."""
        self.availability_calls.append("unavailable")

    async def mark_available(self) -> None:
        """Record an available marker."""
        self.availability_calls.append("available")

    async def sleep(self, seconds: float) -> None:  # noqa: ARG002
        """No-op sleep for tests — completes instantly."""

    @property
    def shutdown_requested(self) -> bool:
        """Return the current shutdown flag value."""
        return self._shutdown

    def request_shutdown(self) -> None:
        """Raise the shutdown flag so a handler loop exits at its next check."""
        self._shutdown = True
