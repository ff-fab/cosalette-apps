"""Async testing utilities.

These utilities help write deterministic async tests by avoiding
timing-based synchronization (fixed sleeps) in favour of condition-based
polling with timeouts.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


async def wait_for_condition(
    condition: Callable[[], bool],
    *,
    timeout: float = 1.0,
    interval: float = 0.005,
    description: str = "condition",
) -> None:
    """Poll until condition() returns True, or raise TimeoutError.

    Args:
        condition: Zero-argument callable returning bool.
        timeout: Maximum seconds to wait before raising TimeoutError.
        interval: Seconds between condition checks.
        description: Human-readable description for the timeout error message.

    Raises:
        TimeoutError: If condition not met within timeout.
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition():
            return
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {description}")
