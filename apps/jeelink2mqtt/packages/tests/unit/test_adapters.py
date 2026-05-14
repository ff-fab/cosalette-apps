"""Unit tests for jeelink2mqtt.adapters.

Test Techniques Used:
- State Transition Testing: Adapter lifecycle (open → callback → inject → close)
- Error Guessing: inject without callback raises RuntimeError
- Specification-based Testing: No-op methods don't crash; FakeJeeLinkAdapter health_check
- Mock Testing: Async context manager lifecycle
- Reopen Semantics: Queue reset between adapter sessions
- Thread-safety Regression: framework callback dispatched via call_soon_threadsafe
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from jeelink2mqtt.adapters import FakeJeeLinkAdapter, PyLaCrosseAdapter
from jeelink2mqtt.models import SensorReading

# ======================================================================
# FakeJeeLinkAdapter lifecycle
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterLifecycle:
    """State Transition tests for FakeJeeLinkAdapter open/close lifecycle."""

    async def test_open_marks_adapter_open(self) -> None:
        """open() sets the internal _open flag.

        Technique: State Transition — closed → open.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act
        await adapter.open()

        # Assert
        assert adapter._open is True

    async def test_close_marks_adapter_closed(self) -> None:
        """close() clears the _open flag.

        Technique: State Transition — open → closed.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()

        # Act
        await adapter.close()

        # Assert
        assert adapter._open is False

    async def test_close_clears_callback(self, make_reading) -> None:
        """close() removes the registered callback.

        Technique: State Transition — callback registered → cleared.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(lambda r: None)

        # Act
        await adapter.close()

        # Assert — inject should now raise because callback is gone
        with pytest.raises(RuntimeError, match="No callback registered"):
            adapter.inject(make_reading())


@pytest.mark.unit
class TestFakeJeeLinkAdapterInject:
    """Specification-based tests for inject/inject_batch."""

    def test_inject_without_callback_raises_runtime_error(self, make_reading) -> None:
        """inject() raises RuntimeError when no callback is registered.

        Technique: Error Guessing — missing precondition.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert
        with pytest.raises(RuntimeError, match="No callback registered"):
            adapter.inject(make_reading())

    def test_inject_calls_callback_with_reading(self, make_reading) -> None:
        """inject() forwards the reading to the registered callback.

        Technique: Specification-based — callback invocation.
        """
        # Arrange
        received: list[SensorReading] = []
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(received.append)
        reading = make_reading(sensor_id=42, temperature=21.5)

        # Act
        adapter.inject(reading)

        # Assert
        assert len(received) == 1
        assert received[0] is reading
        assert received[0].sensor_id == 42

    def test_inject_batch_calls_callback_for_each(self, make_reading) -> None:
        """inject_batch() invokes the callback once per reading.

        Technique: Specification-based — batch processing contract.
        """
        # Arrange
        received: list[SensorReading] = []
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(received.append)
        readings = [make_reading(sensor_id=i) for i in range(5)]

        # Act
        adapter.inject_batch(readings)

        # Assert
        assert len(received) == 5
        assert [r.sensor_id for r in received] == [0, 1, 2, 3, 4]

    def test_inject_batch_empty_list_is_noop(self) -> None:
        """inject_batch([]) with callback doesn't call it.

        Technique: Boundary Value Analysis — empty input.
        """
        # Arrange
        call_count = 0

        def counter(_: SensorReading) -> None:
            nonlocal call_count
            call_count += 1

        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(counter)

        # Act
        adapter.inject_batch([])

        # Assert
        assert call_count == 0


@pytest.mark.unit
class TestFakeJeeLinkAdapterNoOps:
    """Specification-based tests — no-op methods don't crash."""

    async def test_start_scan_is_noop(self) -> None:
        """start_scan() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        await adapter.start_scan()

    async def test_stop_scan_is_noop(self) -> None:
        """stop_scan() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        await adapter.stop_scan()

    def test_set_led_is_noop(self) -> None:
        """set_led() executes without error.

        Technique: Specification-based — no-op contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert — should not raise
        adapter.set_led(True)
        adapter.set_led(False)


# ======================================================================
# FakeJeeLinkAdapter async context manager
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterAsyncContext:
    """Async context manager tests for FakeJeeLinkAdapter."""

    async def test_async_context_manager_lifecycle(self) -> None:
        """Async context manager opens and closes adapter correctly.

        Technique: State Transition — context manager lifecycle.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert
        async with adapter:
            assert adapter._open is True
            assert adapter._scanning is True

        # After exit, adapter should be closed
        assert adapter._open is False
        assert adapter._scanning is False

    async def test_async_context_manager_returns_self(self) -> None:
        """__aenter__ returns the adapter instance.

        Technique: Specification-based — context manager contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act / Assert
        async with adapter as entered:
            assert entered is adapter


# ======================================================================
# FakeJeeLinkAdapter async iterator
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterAsyncIterator:
    """Async iterator tests for FakeJeeLinkAdapter."""

    async def test_async_iterator_yields_injected_readings(self, make_reading) -> None:
        """Async iterator yields readings injected via inject_async.

        Technique: Specification-based — async iteration contract.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()
        reading1 = make_reading(sensor_id=1, temperature=20.0)
        reading2 = make_reading(sensor_id=2, temperature=21.0)

        # Act
        adapter.inject_async(reading1)
        adapter.inject_async(reading2)

        # Assert
        result1 = await anext(adapter)
        result2 = await anext(adapter)
        assert result1 == reading1
        assert result2 == reading2

    async def test_async_iterator_stops_on_close(self, make_reading) -> None:
        """Async iterator raises StopAsyncIteration when adapter is closed.

        Technique: State Transition — iterator termination.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()

        # Act
        await adapter.close()

        # Assert
        with pytest.raises(StopAsyncIteration):
            await anext(adapter)

    async def test_async_iterator_stays_exhausted(self, make_reading) -> None:
        """Closed iterator continues to raise StopAsyncIteration (PEP 525 compliance).

        Technique: Error Guessing — verify iterator stays exhausted after close.
        PEP 525 requires that once exhausted, an async iterator must keep raising
        StopAsyncIteration instead of blocking.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()
        await adapter.close()

        # First call raises StopAsyncIteration
        with pytest.raises(StopAsyncIteration):
            await anext(adapter)

        # Subsequent calls must also raise immediately, not block
        with pytest.raises(StopAsyncIteration):
            await anext(adapter)

    async def test_inject_populates_both_callback_and_iterator(
        self, make_reading
    ) -> None:
        """inject() feeds both callback and async iterator patterns.

        Technique: Specification-based — dual population contract.
        """
        # Arrange
        received_callback: list[SensorReading] = []
        adapter = FakeJeeLinkAdapter()
        adapter.register_callback(received_callback.append)
        reading = make_reading(sensor_id=42, temperature=23.5)

        # Act
        adapter.inject(reading)

        # Assert - callback received reading
        assert len(received_callback) == 1
        assert received_callback[0] == reading

        # Assert - iterator also has reading
        result = await anext(adapter)
        assert result == reading


# ======================================================================
# FakeJeeLinkAdapter reopen semantics
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterReopen:
    """State Transition tests for FakeJeeLinkAdapter reopen semantics.

    Validates that open() after close() resets the queue so stale sentinel
    values from the previous session do not poison the new one.
    """

    async def test_reopen_clears_queue_state(self, make_reading) -> None:
        """open() after close() clears queue to prevent stale readings.

        Technique: State Transition — closed → reopen.
        Regression: ensures sentinel from first close() does not immediately
        terminate iteration in the second session.
        """
        adapter = FakeJeeLinkAdapter()

        # First session: open → inject → close
        await adapter.open()
        reading_session1 = make_reading(sensor_id=99, temperature=25.0)
        adapter.inject_async(reading_session1)
        await adapter.close()

        # Second session: reopen → inject new reading
        await adapter.open()
        reading_session2 = make_reading(sensor_id=100, temperature=30.0)
        adapter.inject_async(reading_session2)

        # Should get the new reading, not StopAsyncIteration from close sentinel
        result = await anext(adapter)
        assert result.sensor_id == 100
        assert result.temperature == 30.0


# ======================================================================
# PyLaCrosseAdapter — framework callback thread safety
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterFrameworkCallback:
    """Regression: framework callback must be dispatched via call_soon_threadsafe.

    cosalette 0.4's run_stream registers ``stream.put`` as the callback via
    :meth:`PyLaCrosseAdapter.register_callback`.  The ``_wrapper`` inside
    :meth:`start_scan` runs on the pylacrosse serial-reader thread, which is
    **not** the asyncio event-loop thread.  Calling ``stream.put`` (or any
    :class:`asyncio.Queue` method) directly from that thread is a data-race —
    it must be marshalled to the event loop via
    ``self._loop.call_soon_threadsafe()``.
    """

    async def test_framework_callback_dispatched_via_call_soon_threadsafe(
        self,
    ) -> None:
        """start_scan() uses call_soon_threadsafe, never calls framework_cb directly.

        Regression: the previous version called ``framework_cb(reading)``
        directly from the pylacrosse thread.  cosalette's Stream.put wraps
        asyncio.Queue, which is NOT thread-safe.  Cross-thread direct calls
        can silently corrupt the queue or drop readings.

        Technique: Mock Testing — intercept self._loop.call_soon_threadsafe
        and verify it receives the callback reference; assert the callback is
        never invoked directly from the wrapper.
        """
        # Build a minimal mock pylacrosse module (lazy import inside open()).
        captured_wrapper: dict = {}
        mock_lacrosse = MagicMock()
        mock_lacrosse.register_all.side_effect = lambda w: captured_wrapper.update(
            {"fn": w}
        )
        mock_pylacrosse = MagicMock()
        mock_pylacrosse.LaCrosse.return_value = mock_lacrosse

        direct_calls: list = []
        framework_cb = MagicMock(side_effect=lambda r: direct_calls.append(r))

        with patch.dict(sys.modules, {"pylacrosse": mock_pylacrosse}):
            adapter = PyLaCrosseAdapter("/dev/ttyUSB0", 57600)
            await adapter.open()
            adapter.register_callback(framework_cb)

            # Replace _loop with a mock to intercept call_soon_threadsafe.
            # Must happen BEFORE start_scan() so the wrapper captures the mock.
            mock_loop = MagicMock()
            adapter._loop = mock_loop

            await adapter.start_scan()

        assert "fn" in captured_wrapper, "register_all() was never called"
        wrapper = captured_wrapper["fn"]

        # Build a valid-looking sensor (attributes coerced by _convert_sensor_to_reading).
        sensor = MagicMock()
        sensor.sensorid = "42"
        sensor.temperature = "20.5"
        sensor.humidity = "60"
        sensor.low_battery = False

        # Trigger the wrapper as if running on the pylacrosse serial-reader thread.
        # Two-argument call matches the real pylacrosse register_all() call signature.
        wrapper(sensor, None)

        # framework_cb must NOT have been called directly from the wrapper.
        assert direct_calls == [], (
            "framework_cb was invoked directly from the wrapper thread — "
            "this is a thread-safety violation; use call_soon_threadsafe instead"
        )

        # call_soon_threadsafe must have been called with a dispatcher closure,
        # not framework_cb directly — the closure catches/logs exceptions locally.
        mock_loop.call_soon_threadsafe.assert_called_once()
        dispatched_fn = mock_loop.call_soon_threadsafe.call_args[0][0]
        assert callable(dispatched_fn), (
            "call_soon_threadsafe must receive a callable dispatcher"
        )
        assert dispatched_fn is not framework_cb, (
            "call_soon_threadsafe must receive a dispatcher closure, "
            "not framework_cb directly"
        )

        # Invoke the dispatcher manually and assert framework_cb receives the
        # converted SensorReading with the expected field values.
        dispatched_fn()
        framework_cb.assert_called_once()
        reading = framework_cb.call_args[0][0]
        assert isinstance(reading, SensorReading)
        assert reading.sensor_id == 42
        assert reading.temperature == 20.5
        assert reading.humidity == 60
        assert reading.low_battery is False


# ======================================================================
# FakeJeeLinkAdapter health check
# ======================================================================


@pytest.mark.unit
class TestFakeJeeLinkAdapterHealthCheck:
    """Specification-based tests for FakeJeeLinkAdapter.health_check."""

    async def test_health_check_returns_true_when_open(self) -> None:
        """health_check returns True when the adapter is open.

        Technique: Specification-based — open state → healthy.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()

        # Act
        result = await adapter.health_check()

        # Assert
        assert result is True

    async def test_health_check_returns_false_when_closed(self) -> None:
        """health_check returns False when the adapter has been closed.

        Technique: State Transition — open → close → health_check unhealthy.
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()
        await adapter.open()
        await adapter.close()

        # Act
        result = await adapter.health_check()

        # Assert
        assert result is False

    async def test_health_check_returns_false_when_never_opened(self) -> None:
        """health_check returns False on a fresh adapter that was never opened.

        Technique: Boundary Value Analysis — initial state (never opened).
        """
        # Arrange
        adapter = FakeJeeLinkAdapter()

        # Act
        result = await adapter.health_check()

        # Assert
        assert result is False
