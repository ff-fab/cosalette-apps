"""Hardware adapter implementations for jeelink2mqtt.

Production adapter wraps ``pylacrosse`` via lazy import (ADR-003).
Fake adapter produces configurable readings for testing and dry-run.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from jeelink2mqtt.models import SensorReading

logger = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 100
"""Maximum unprocessed readings to buffer before dropping."""


class PyLaCrosseAdapter:
    """Production adapter wrapping :mod:`pylacrosse` via lazy import.

    The ``pylacrosse`` package is imported *inside methods* rather than
    at module level (ADR-003), so jeelink2mqtt can be imported on
    developer machines that lack ``pyserial``.

    Contains the thread-to-async bridge internally, exposing async
    iteration semantics to consumers.
    """

    def __init__(self, port: str, baud_rate: int) -> None:
        self._port = port
        self._baud_rate = baud_rate
        self._lacrosse: Any = None
        self._queue: asyncio.Queue[SensorReading | None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._framework_callback: Callable[[SensorReading], None] | None = None

    async def open(self) -> None:
        """Lazily import pylacrosse, create the instance, and open."""
        import pylacrosse  # noqa: PLC0415 — lazy import by design

        self._lacrosse = pylacrosse.LaCrosse(self._port, self._baud_rate)
        self._lacrosse.open()

        # Set up async infrastructure
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(_QUEUE_MAXSIZE)
        self._closed = False

    def _convert_sensor_to_reading(self, sensor: Any) -> SensorReading | None:
        """Convert pylacrosse sensor object to SensorReading.

        Args:
            sensor: LaCrosseSensor object with attributes sensorid, temperature,
                   humidity, low_battery, new_battery

        Returns:
            SensorReading object, or None if sensor is invalid
        """
        if not hasattr(sensor, "sensorid"):
            logger.warning("Invalid sensor object - missing sensorid: %r", sensor)
            return None

        try:
            sensor_id = int(sensor.sensorid)
            temperature = float(sensor.temperature)
            humidity = int(sensor.humidity)
            low_battery = bool(sensor.low_battery)
        except AttributeError as e:
            logger.warning("Sensor missing expected attribute: %s", e)
            return None
        except (TypeError, ValueError) as e:
            logger.warning("Sensor attribute type coercion failed: %s", e)
            return None

        if sensor_id < 0:
            logger.warning(
                "Invalid sensor_id %d (must be non-negative) — dropping", sensor_id
            )
            return None
        if not math.isfinite(temperature):
            logger.warning(
                "Non-finite temperature %r for sensor %d — dropping",
                temperature,
                sensor_id,
            )
            return None
        if not (-50.0 <= temperature <= 100.0):
            logger.warning(
                "Implausible temperature %.1f for sensor %d — dropping",
                temperature,
                sensor_id,
            )
            return None
        if not (0 <= humidity <= 100):
            logger.warning(
                "Invalid humidity %d for sensor %d — dropping", humidity, sensor_id
            )
            return None

        return SensorReading(
            sensor_id=sensor_id,
            temperature=temperature,
            humidity=humidity,
            low_battery=low_battery,
            timestamp=datetime.now(UTC),
        )

    async def close(self) -> None:
        """Close the underlying serial connection if open."""
        if self._lacrosse is not None:
            self._lacrosse.close()
            self._lacrosse = None

        self._framework_callback = None

        # Signal iterator termination
        if self._queue is not None:
            try:
                self._queue.put_nowait(None)  # Sentinel to end iteration
            except asyncio.QueueFull:
                pass  # Queue might be full; this is fine for shutdown

        self._loop = None

    async def start_scan(self) -> None:
        """Start scanning for incoming LaCrosse frames.

        Creates a single internal wrapper that either forwards to the framework
        callback stored by :meth:`register_callback` (cosalette 0.4 path), or
        enqueues into the async iterator queue (legacy path).
        """
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)

        if self._queue is None or self._loop is None:
            msg = "Async infrastructure not ready — call open() first"
            raise RuntimeError(msg)

        framework_cb = self._framework_callback

        def _wrapper(sensor: Any, user_data: Any = None) -> None:
            """Single callback bridging pylacrosse thread → cosalette stream or queue."""
            try:
                reading = self._convert_sensor_to_reading(sensor)
                if reading is None:
                    return

                if framework_cb is not None:
                    # Framework path: marshal to the event loop via
                    # call_soon_threadsafe. cosalette 0.4's Stream.put (and
                    # asyncio.Queue) are NOT thread-safe — they must only be
                    # called from the event-loop thread. This wrapper runs on
                    # the pylacrosse serial reader thread, so we schedule the
                    # callback on the event loop instead of invoking it directly.
                    #
                    # A small dispatcher closure is scheduled rather than the
                    # framework_cb directly, so that any callback exception is
                    # caught and logged here rather than propagating to asyncio's
                    # unhandled-exception handler (which would log a less specific
                    # message and suppress our structured error reporting).
                    loop = self._loop
                    if loop is not None:

                        def _dispatch_reading() -> None:
                            try:
                                framework_cb(reading)
                            except Exception:
                                logger.exception(
                                    "Error dispatching reading to framework callback"
                                )

                        try:
                            loop.call_soon_threadsafe(_dispatch_reading)
                        except RuntimeError:
                            logger.debug(
                                "Failed to dispatch reading to framework "
                                "callback during shutdown"
                            )
                else:
                    # Legacy async-iterator path: bridge via call_soon_threadsafe.
                    if self._loop is not None and self._queue is not None:
                        queue = self._queue

                        def _enqueue(r: SensorReading) -> None:
                            try:
                                queue.put_nowait(r)
                            except asyncio.QueueFull:
                                logger.warning(
                                    "Queue full — dropping reading from sensor %d",
                                    r.sensor_id,
                                )

                        try:
                            self._loop.call_soon_threadsafe(_enqueue, reading)
                        except RuntimeError:
                            logger.debug("Failed to enqueue reading during shutdown")
            except Exception:
                # Thread boundary: this runs on pylacrosse's serial reader
                # thread, outside cosalette's asyncio error isolation.
                # Letting exceptions propagate would kill the reader thread
                # and silently stop all frame processing.
                logger.exception("Error processing sensor reading: %r", sensor)

        self._lacrosse.register_all(_wrapper)
        self._lacrosse.start_scan()

    async def stop_scan(self) -> None:
        """No-op — pylacrosse doesn't expose a discrete stop-scan; use close."""
        logger.debug("stop_scan() is a no-op for pylacrosse; call close() instead")

    async def health_check(self) -> bool:
        """Return True if the serial port device file is still present.

        Probes OS-level device-file existence via a thread pool executor so
        the check is non-blocking and does not disturb the open port.
        """
        import os  # noqa: PLC0415 — deferred to avoid import at module level

        return await asyncio.to_thread(os.path.exists, self._port)

    def register_callback(
        self,
        callback: Callable[[SensorReading], None],
    ) -> None:
        """Store the framework callback for use by :meth:`start_scan`.

        The callback is called with each decoded :class:`SensorReading` when
        :meth:`start_scan` is running.  The actual pylacrosse registration and
        sensor-object conversion happen inside :meth:`start_scan` so that only
        one callback is registered with the underlying library regardless of
        call order.

        This is the cosalette 0.4 :class:`StreamablePort` contract:
        ``open()`` → ``register_callback(stream.put)`` → ``start_scan()``.
        """
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)

        self._framework_callback = callback

    def set_led(self, enabled: bool) -> None:
        """Control the JeeLink on-board LED."""
        if self._lacrosse is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)
        self._lacrosse.led_mode_state(enabled)

    def __aiter__(self) -> AsyncIterator[SensorReading]:
        """Return an async iterator over sensor readings."""
        return self

    async def __anext__(self) -> SensorReading:
        """Get the next sensor reading."""
        if self._closed:
            raise StopAsyncIteration
        if self._queue is None:
            msg = "Adapter not open — call open() first"
            raise RuntimeError(msg)

        reading = await self._queue.get()
        if reading is None:
            self._closed = True
            raise StopAsyncIteration
        return reading

    async def __aenter__(self) -> PyLaCrosseAdapter:
        """Enter async context manager."""
        await self.open()
        try:
            await self.start_scan()
        except Exception:
            # If start_scan fails after open, clean up the connection
            await self.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager."""
        await self.stop_scan()
        await self.close()


class FakeJeeLinkAdapter:
    """In-memory adapter for ``--dry-run`` mode and testing.

    Readings are injected programmatically via :meth:`inject` or
    :meth:`inject_batch`, making this adapter ideal for deterministic
    tests. Supports async iteration while maintaining simple injection
    helpers.
    """

    def __init__(self) -> None:
        self._callback: Callable[[SensorReading], None] | None = None
        self._open = False
        self._queue: asyncio.Queue[SensorReading | None] = asyncio.Queue()
        self._scanning = False
        self._closed = False

    async def open(self) -> None:
        """Mark the adapter as open and reset the queue."""
        self._open = True
        # Reset the queue and closed flag for reopen support
        self._queue = asyncio.Queue()
        self._closed = False

    async def close(self) -> None:
        """Mark the adapter as closed and clear the callback."""
        self._open = False
        self._scanning = False
        self._callback = None
        # Signal iterator termination
        try:
            self._queue.put_nowait(None)  # Sentinel to end iteration
        except asyncio.QueueFull:
            pass  # Queue might be full; this is fine for shutdown

    async def start_scan(self) -> None:
        """No-op — readings are injected manually."""
        self._scanning = True

    async def stop_scan(self) -> None:
        """No-op — readings are injected manually."""

    async def health_check(self) -> bool:
        """Return True when the adapter is open."""
        return self._open

    def register_callback(
        self,
        callback: Callable[[SensorReading], None],
    ) -> None:
        """Store the callback for later use by :meth:`inject`."""
        self._callback = callback

    def set_led(self, enabled: bool) -> None:  # noqa: ARG002
        """No-op — fake adapter has no LED."""

    def __aiter__(self) -> AsyncIterator[SensorReading]:
        """Return an async iterator over sensor readings."""
        return self

    async def __anext__(self) -> SensorReading:
        """Get the next sensor reading."""
        if self._closed:
            raise StopAsyncIteration
        reading = await self._queue.get()
        if reading is None:
            self._closed = True
            raise StopAsyncIteration
        return reading

    async def __aenter__(self) -> FakeJeeLinkAdapter:
        """Enter async context manager."""
        await self.open()
        await self.start_scan()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager."""
        await self.stop_scan()
        await self.close()

    # -- Test helpers ------------------------------------------------------

    def inject(self, reading: SensorReading) -> None:
        """Directly invoke the stored callback with a single reading.

        This is the primary test-helper method.  Raises ``RuntimeError``
        if no callback has been registered.

        Also injects into the async iterator queue for new async iteration pattern.
        """
        if self._callback is None:
            msg = "No callback registered — call register_callback() first"
            raise RuntimeError(msg)
        self._callback(reading)

        # Also inject into async iterator queue
        try:
            self._queue.put_nowait(reading)
        except asyncio.QueueFull:
            # In tests, queue shouldn't fill up, but handle gracefully
            pass

    def inject_batch(self, readings: list[SensorReading]) -> None:
        """Invoke the stored callback once per reading in *readings*."""
        for reading in readings:
            self.inject(reading)

    def inject_async(self, reading: SensorReading) -> None:
        """Inject a reading into the async iterator queue.

        Use this for testing async iteration patterns.
        """
        try:
            self._queue.put_nowait(reading)
        except asyncio.QueueFull:
            # In tests, queue shouldn't fill up, but handle gracefully
            pass

    def inject_batch_async(self, readings: list[SensorReading]) -> None:
        """Inject multiple readings into the async iterator queue."""
        for reading in readings:
            self.inject_async(reading)
