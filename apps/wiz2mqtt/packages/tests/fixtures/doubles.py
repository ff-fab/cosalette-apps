"""Shared test doubles for wiz2mqtt tests.

Mirrors jeelink2mqtt's ``tests/fixtures/doubles.py`` — a minimal fake for
``cosalette.DeviceContext``, centralised so changes to the framework API
only need updating in one place.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeDeviceContext:
    """Minimal fake for ``cosalette.DeviceContext``.

    Captures publish/availability calls for entity-tick tests.
    """

    published_state: list[dict[str, object]] = field(default_factory=list)
    availability_calls: list[str] = field(default_factory=list)
    """Sequence of ``"available"``/``"unavailable"`` markers, in call order."""

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
