"""Fake adapters for testing and dry-run mode.

FakeWallpanel is an in-memory state machine implementing WallpanelPort.
FakeWol records wake() calls for assertion in tests.

Neither touches hardware — safe for unit tests and dry-run mode.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

logger = logging.getLogger(__name__)


class FakeWallpanel:
    """In-memory test double for WallpanelPort.

    Tracks brightness, screen state, and reachability. When not reachable,
    getters return None and mutators raise ConnectionError.

    Attributes:
        brightness: Current brightness value.
        max_brightness: Maximum brightness value.
        screen_state: True if screen is on, False if off.
        reachable: Whether the fake wallpanel is reachable.
        power_state: Last power action ("running", "hibernating", "suspended").
    """

    def __init__(
        self,
        *,
        brightness: int = 0,
        max_brightness: int = 7812,
        screen_state: bool = True,
        reachable: bool = True,
    ) -> None:
        self.brightness = brightness
        self.max_brightness = max_brightness
        self.screen_state = screen_state
        self.reachable = reachable
        self.power_state = "running"

    def _check_reachable(self) -> None:
        """Raise ConnectionError if wallpanel is not reachable."""
        if not self.reachable:
            msg = "FakeWallpanel is not reachable"
            raise ConnectionError(msg)

    async def set_brightness(self, value: int) -> None:
        """Set brightness in memory."""
        self._check_reachable()
        self.brightness = value
        logger.info("set_brightness(%d)", value)

    async def get_brightness(self) -> int | None:
        """Return brightness or None if unreachable."""
        if not self.reachable:
            return None
        return self.brightness

    async def get_max_brightness(self) -> int:
        """Return max brightness."""
        return self.max_brightness

    async def screen_on(self) -> None:
        """Turn screen on in memory."""
        self._check_reachable()
        self.screen_state = True
        logger.info("screen_on()")

    async def screen_off(self) -> None:
        """Turn screen off in memory."""
        self._check_reachable()
        self.screen_state = False
        logger.info("screen_off()")

    async def get_screen_state(self) -> bool | None:
        """Return screen state or None if unreachable."""
        if not self.reachable:
            return None
        return self.screen_state

    async def hibernate(self) -> None:
        """Simulate hibernate: set unreachable and power_state."""
        self._check_reachable()
        self.power_state = "hibernating"
        self.reachable = False
        logger.info("hibernate()")

    async def suspend(self) -> None:
        """Simulate suspend: set unreachable and power_state."""
        self._check_reachable()
        self.power_state = "suspended"
        self.reachable = False
        logger.info("suspend()")

    async def is_reachable(self) -> bool:
        """Return current reachability."""
        return self.reachable

    def set_reachable(self, reachable: bool) -> None:
        """Test helper: set reachability state."""
        self.reachable = reachable
        if reachable:
            self.power_state = "running"

    def set_brightness_state(self, value: int) -> None:
        """Test helper: set brightness without reachability check."""
        self.brightness = value

    async def __aenter__(self) -> Self:
        """Enter async context (no-op for fake)."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context (no-op for fake)."""


class FakeWol:
    """Test double for WolPort that records wake() calls.

    Attributes:
        calls: List of (mac, broadcast) tuples from each wake() invocation.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def wake(self, mac: str, broadcast: str) -> None:
        """Record wake call for later assertion."""
        self.calls.append((mac, broadcast))
        logger.info("wake(mac=%s, broadcast=%s)", mac, broadcast)
