# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Async testing utilities.

These utilities help write deterministic async tests by avoiding
timing-based synchronization (fixed sleeps) in favor of condition-based
polling with timeouts.
"""

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

    This is more robust than fixed sleeps for verifying async state changes.
    Use this when you need to wait for a side effect to complete (e.g.,
    subscriber cleanup, queue drain) rather than coordinating concurrent
    coroutines (use asyncio.Event for that).

    Args:
        condition: Zero-argument callable returning bool. Typically a lambda
            checking some observable state,
            e.g., `lambda: store.subscriber_count() == 0`.
        timeout: Maximum seconds to wait before raising TimeoutError.
        interval: Seconds between condition checks. Default 5ms balances
            responsiveness with CPU overhead.
        description: Human-readable description for the timeout error message.

    Raises:
        TimeoutError: If condition not met within timeout.

    Example:
        ```python
        # Wait for subscriber cleanup after task cancellation
        await wait_for_condition(
            lambda: store.subscriber_count() == 0,
            description="subscriber cleanup",
        )
        ```
    """
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if condition():
            return
        await asyncio.sleep(interval)
    raise TimeoutError(f"Timed out waiting for {description}")
