"""Hardware adapter implementations for jeelink2mqtt.

Production adapter wraps ``pylacrosse`` via lazy import (ADR-003).
Fake adapter produces configurable readings for testing and dry-run.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from jeelink2mqtt.models import SensorReading

logger = logging.getLogger(__name__)

_FRAME_RE = re.compile(r"id=(\d+)\s+t=(-?[\d.]+)\s+h=(\d+)\s+nbat=(\d+)")
"""Regex matching pylacrosse's string sensor format (supports negative temps)."""


class PyLaCrosseAdapter:
    """Production adapter wrapping :mod:`pylacrosse` via lazy import.

    The ``pylacrosse`` package is imported *inside methods* rather than
    at module level (ADR-003), so jeelink2mqtt can be imported on
    developer machines that lack ``pyserial``.
    """

    def __init__(self, port: str, baud_rate: int) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._lacrosse: Any = None

    def open(self) -> None:
        """Lazily import pylacrosse, create the instance, and open."""
        import pylacrosse  # noqa: PLC0415 — lazy import by design

        self._lacrosse = pylacrosse.LaCrosse(self._port, self._baud_rate)
        self._lacrosse.open()

    def close(self) -> None:
        """Close the underlying serial connection if open."""
        if self._lacrosse is not None:
            self._lacrosse.close()
            self._lacrosse = None

    def start_scan(self) -> None:
        """Start scanning for incoming LaCrosse frames."""
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)
        self._lacrosse.start_scan()

    def stop_scan(self) -> None:
        """No-op — pylacrosse doesn't expose a discrete stop-scan; use close."""
        logger.debug("stop_scan() is a no-op for pylacrosse; call close() instead")

    def register_callback(
        self,
        callback: Callable[[SensorReading], None],
    ) -> None:
        """Register a callback, translating pylacrosse strings to SensorReading.

        The wrapper parses the pylacrosse sensor string format
        (``"id=X t=Y.Y h=Z nbat=N"``) into a :class:`SensorReading`
        and forwards it to the caller's callback.  Unparsable frames
        (regex mismatch) are logged as warnings and skipped; all other
        errors propagate to the framework's error handling.
        """
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)

        def _wrapper(sensor_string: str) -> None:
            match = _FRAME_RE.search(sensor_string)
            if match is None:
                logger.warning("Unparsable LaCrosse frame: %r", sensor_string)
                return

            reading = SensorReading(
                sensor_id=int(match.group(1)),
                temperature=float(match.group(2)),
                humidity=int(match.group(3)),
                low_battery=match.group(4) != "0",
                timestamp=datetime.now(UTC),
            )
            callback(reading)

        self._lacrosse.register_all(_wrapper)

    def set_led(self, enabled: bool) -> None:
        """Control the JeeLink on-board LED."""
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)
        self._lacrosse.led_mode_state(enabled)


class FakeJeeLinkAdapter:
    """In-memory adapter for ``--dry-run`` mode and testing.

    Readings are injected programmatically via :meth:`inject` or
    :meth:`inject_batch`, making this adapter ideal for deterministic
    tests.
    """

    def __init__(self) -> None:
        self._callback: Callable[[SensorReading], None] | None = None
        self._open = False

    def open(self) -> None:
        """Mark the adapter as open."""
        self._open = True

    def close(self) -> None:
        """Mark the adapter as closed and clear the callback."""
        self._open = False
        self._callback = None

    def start_scan(self) -> None:
        """No-op — readings are injected manually."""

    def stop_scan(self) -> None:
        """No-op — readings are injected manually."""

    def register_callback(
        self,
        callback: Callable[[SensorReading], None],
    ) -> None:
        """Store the callback for later use by :meth:`inject`."""
        self._callback = callback

    def set_led(self, enabled: bool) -> None:  # noqa: ARG002
        """No-op — fake adapter has no LED."""

    # -- Test helpers ------------------------------------------------------

    def inject(self, reading: SensorReading) -> None:
        """Directly invoke the stored callback with a single reading.

        This is the primary test-helper method.  Raises ``RuntimeError``
        if no callback has been registered.
        """
        if self._callback is None:
            msg = "No callback registered — call register_callback() first"
            raise RuntimeError(msg)
        self._callback(reading)

    def inject_batch(self, readings: list[SensorReading]) -> None:
        """Invoke the stored callback once per reading in *readings*."""
        for reading in readings:
            self.inject(reading)
