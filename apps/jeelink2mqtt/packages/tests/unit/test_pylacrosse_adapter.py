"""Unit tests for PyLaCrosseAdapter with mocked pylacrosse.

The ``pylacrosse`` package is a hardware library that requires a
physical JeeLink USB receiver, so we mock it entirely via
``sys.modules`` patching.  This exercises all PyLaCrosseAdapter
methods that were previously uncovered (lines 32–100 of adapters.py).

Test Techniques Used:
- State Transition Testing: Adapter lifecycle (init → open → scan → close)
- Error Guessing: Methods called before open() raise RuntimeError
- Specification-based: Callback wrapping and frame parsing
- Branch/Condition Coverage: Parse success, parse failure, callback exception
- Async Iterator Testing: PEP 525 compliance, iterator exhaustion
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from jeelink2mqtt.models import SensorReading

# ======================================================================
# Fixtures
# ======================================================================


class FakeLaCrosseSensor:
    """Fake sensor object matching pylacrosse 0.4 LaCrosseSensor interface."""

    def __init__(
        self,
        sensorid: int,
        temperature: float,
        humidity: int,
        low_battery: bool = False,
        new_battery: bool = False,
    ):
        self.sensorid = sensorid
        self.temperature = temperature
        self.humidity = humidity
        self.low_battery = low_battery
        self.new_battery = new_battery


@pytest.fixture()
def mock_pylacrosse():
    """Mock pylacrosse module injected into ``sys.modules``.

    Yields ``(mock_module, mock_instance)`` so tests can inspect calls
    made to the ``LaCrosse`` class and its instance methods.
    """
    mock_module = MagicMock()
    mock_instance = MagicMock()
    mock_module.LaCrosse.return_value = mock_instance
    with patch.dict("sys.modules", {"pylacrosse": mock_module}):
        yield mock_module, mock_instance


@pytest.fixture()
async def opened_adapter(mock_pylacrosse):
    """PyLaCrosseAdapter that has already been ``open()``-ed.

    Returns ``(adapter, mock_instance)`` with the mock's initial
    ``open()`` call cleared via ``reset_mock()``.
    """
    from jeelink2mqtt.adapters import PyLaCrosseAdapter

    _, mock_instance = mock_pylacrosse
    adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
    await adapter.open()
    mock_instance.reset_mock()  # Clear the open() call
    return adapter, mock_instance


# ======================================================================
# Lifecycle: open / close
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterLifecycle:
    """State Transition Testing for open/close lifecycle."""

    async def test_open_imports_and_creates_lacrosse(
        self, mock_pylacrosse: tuple[MagicMock, MagicMock]
    ) -> None:
        """open() lazily imports pylacrosse, creates LaCrosse, and opens it.

        Technique: Specification-based — verifying the lazy-import contract
        documented in ADR-003.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        mock_module, mock_instance = mock_pylacrosse

        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act
        await adapter.open()

        # Assert
        mock_module.LaCrosse.assert_called_once_with("/dev/ttyUSB0", 57600)
        mock_instance.open.assert_called_once()

    async def test_close_closes_and_clears(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """close() delegates to the underlying instance and sets it to None.

        Technique: State Transition — open → close nullifies internal state.
        """
        adapter, mock_instance = opened_adapter

        # Act
        await adapter.close()

        # Assert
        mock_instance.close.assert_called_once()
        assert adapter._lacrosse is None  # noqa: SLF001

    async def test_close_when_not_open_is_noop(self, mock_pylacrosse) -> None:
        """close() on a never-opened adapter is a safe no-op.

        Technique: Error Guessing — calling close before open should
        not raise.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert — no exception
        await adapter.close()


# ======================================================================
# Scanning
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterScanning:
    """State Transition Testing for start_scan / stop_scan."""

    async def test_start_scan_delegates(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """start_scan() delegates to the underlying pylacrosse instance.

        Technique: Specification-based — verifying delegation contract.
        """
        adapter, mock_instance = opened_adapter

        # Act
        await adapter.start_scan()

        # Assert
        mock_instance.start_scan.assert_called_once()

    async def test_start_scan_without_open_raises(self, mock_pylacrosse) -> None:
        """start_scan() before open() raises RuntimeError.

        Technique: Error Guessing — precondition violation.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert
        with pytest.raises(RuntimeError, match="Adapter not open"):
            await adapter.start_scan()

    async def test_stop_scan_does_not_raise(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """stop_scan() is a no-op that logs a debug message.

        Technique: Specification-based — documented no-op behaviour.
        """
        adapter, _ = opened_adapter

        # Act / Assert — no exception raised
        await adapter.stop_scan()


# ======================================================================
# Async context manager
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterAsyncContext:
    """Async context manager lifecycle tests."""

    async def test_aenter_failure_cleans_up_connection(self, mock_pylacrosse) -> None:
        """If start_scan fails during __aenter__, close() is called to cleanup.

        Technique: Error Path Testing — ensure resource cleanup on failure.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        _, mock_instance = mock_pylacrosse
        mock_instance.start_scan.side_effect = RuntimeError("Scan failed")
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert
        with pytest.raises(RuntimeError, match="Scan failed"):
            async with adapter:
                pass  # Should not reach here

        # Verify cleanup was called
        mock_instance.close.assert_called_once()


# ======================================================================
# Callback registration and frame parsing
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterCallback:
    """Branch/Condition Coverage for register_callback and its wrapper."""

    async def test_register_callback_wraps_frame(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Valid pylacrosse frame string is parsed into a SensorReading.

        Technique: Specification-based — happy-path frame parsing via the
        framework lifecycle: register_callback then start_scan.
        """
        adapter, mock_instance = opened_adapter

        # Arrange — framework lifecycle: store callback then start scan
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        await adapter.start_scan()

        # Get the wrapper that was passed to register_all (done inside start_scan)
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act — simulate pylacrosse calling the wrapper; the wrapper
        # schedules a dispatcher on the event loop via call_soon_threadsafe,
        # so we must yield to the loop before asserting side effects.
        fake_sensor = FakeLaCrosseSensor(
            sensorid=42, temperature=21.5, humidity=55, low_battery=False
        )
        wrapper(fake_sensor, None)
        await asyncio.sleep(0)  # let the scheduled dispatcher run

        # Assert
        assert len(received) == 1
        reading = received[0]
        assert reading.sensor_id == 42
        assert reading.temperature == 21.5
        assert reading.humidity == 55
        assert reading.low_battery is False

    async def test_register_callback_parses_low_battery(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """nbat=1 is parsed as low_battery=True.

        Technique: Boundary Value Analysis — boolean boundary (0 vs nonzero).
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        await adapter.start_scan()
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        fake_sensor = FakeLaCrosseSensor(
            sensorid=10, temperature=18.0, humidity=70, low_battery=True
        )
        wrapper(fake_sensor, None)
        await asyncio.sleep(0)  # let the scheduled dispatcher run

        # Assert
        assert len(received) == 1
        assert received[0].low_battery is True

    async def test_register_callback_parses_negative_temperature(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Negative temperature is correctly parsed.

        Technique: Boundary Value Analysis — sign change boundary.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        await adapter.start_scan()
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        fake_sensor = FakeLaCrosseSensor(
            sensorid=7, temperature=-3.2, humidity=90, low_battery=False
        )
        wrapper(fake_sensor, None)
        await asyncio.sleep(0)  # let the scheduled dispatcher run

        # Assert
        assert len(received) == 1
        assert received[0].temperature == -3.2

    def test_register_callback_without_open_raises(self, mock_pylacrosse) -> None:
        """register_callback() before open() raises RuntimeError.

        Technique: Error Guessing — precondition violation.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert
        with pytest.raises(RuntimeError, match="Adapter not open"):
            adapter.register_callback(lambda r: None)

    async def test_register_callback_ignores_unparsable_frame(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """Wrapper logs a warning and skips when frame doesn't match regex.

        Technique: Error Guessing — malformed input from hardware.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        await adapter.start_scan()
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        with caplog.at_level(logging.WARNING):
            # Test with sensor missing sensorid attribute
            class BadSensor:
                pass

            wrapper(BadSensor(), None)

        # Assert — callback was NOT invoked
        assert len(received) == 0
        assert "Invalid sensor object" in caplog.text

    async def test_register_callback_logs_exception_from_callback(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """Exception in callback is logged, not propagated.

        Technique: Error Guessing — callback error on pylacrosse's serial
        reader thread is caught and logged to keep the thread alive.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        def bad_callback(reading: SensorReading) -> None:
            msg = "boom"
            raise ValueError(msg)

        adapter.register_callback(bad_callback)
        await adapter.start_scan()
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act — exception does NOT propagate; dispatcher is scheduled via
        # call_soon_threadsafe so we yield to the loop inside caplog context.
        fake_sensor = FakeLaCrosseSensor(
            sensorid=1, temperature=20.0, humidity=50, low_battery=False
        )
        with caplog.at_level(logging.ERROR):
            wrapper(fake_sensor, None)
            await asyncio.sleep(0)  # let the dispatcher run and log

        # Assert — error is logged by the dispatcher, not asyncio's handler
        assert "Error dispatching reading to framework callback" in caplog.text

    async def test_register_callback_handles_missing_humidity(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """Wrapper logs warning for a sensor missing the humidity attribute.

        Technique: Error Guessing — partial sensor object from hardware.
        """
        adapter, mock_instance = opened_adapter

        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        await adapter.start_scan()
        wrapper = mock_instance.register_all.call_args[0][0]

        class IncompleteSensor:
            sensorid = 99
            temperature = 25.0
            # missing humidity intentionally
            low_battery = False

        with caplog.at_level(logging.WARNING):
            wrapper(IncompleteSensor(), None)

        assert "Sensor missing expected attribute" in caplog.text
        assert len(received) == 0

    async def test_framework_lifecycle_callback_receives_reading(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Full framework lifecycle: open → register_callback → start_scan → frame.

        Proves the cosalette 0.4 StreamablePort contract: register_callback
        stores the callback and start_scan registers exactly ONE wrapper that
        forwards decoded SensorReadings to that callback (not to the queue).

        Technique: Integration — verifies the framework-path contract end-to-end.
        """
        adapter, mock_instance = opened_adapter

        # Arrange — framework path
        received: list[SensorReading] = []
        adapter.register_callback(received.append)  # cosalette calls this first
        await adapter.start_scan()  # then this — only ONE register_all call

        # Exactly one callback registered with pylacrosse
        assert mock_instance.register_all.call_count == 1

        wrapper = mock_instance.register_all.call_args[0][0]

        # Simulate pylacrosse calling the wrapper with a valid frame.
        # The wrapper schedules a dispatcher via call_soon_threadsafe, so
        # we yield to the event loop before asserting the callback result.
        fake_sensor = FakeLaCrosseSensor(
            sensorid=7, temperature=23.1, humidity=60, low_battery=False
        )
        wrapper(fake_sensor, None)
        await asyncio.sleep(0)  # let the scheduled dispatcher run

        # Framework callback received the decoded reading
        assert len(received) == 1
        assert received[0].sensor_id == 7
        assert received[0].temperature == 23.1


# ======================================================================
# LED control
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterLed:
    """Specification-based tests for set_led delegation."""

    def test_set_led_delegates(self, opened_adapter: tuple[object, MagicMock]) -> None:
        """set_led() delegates to the pylacrosse led_mode_state method.

        Technique: Specification-based — verifying delegation.
        """
        adapter, mock_instance = opened_adapter

        # Act
        adapter.set_led(True)

        # Assert
        mock_instance.led_mode_state.assert_called_once_with(True)

    def test_set_led_false(self, opened_adapter: tuple[object, MagicMock]) -> None:
        """set_led(False) passes False to led_mode_state.

        Technique: Equivalence Partitioning — both boolean values.
        """
        adapter, mock_instance = opened_adapter

        # Act
        adapter.set_led(False)

        # Assert
        mock_instance.led_mode_state.assert_called_once_with(False)

    def test_set_led_without_open_raises(self, mock_pylacrosse) -> None:
        """set_led() before open() raises RuntimeError.

        Technique: Error Guessing — precondition violation.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert
        with pytest.raises(RuntimeError, match="Adapter not open"):
            adapter.set_led(True)


# ======================================================================
# start_scan callback behavior
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterStartScan:
    """Branch/Condition Coverage for start_scan's internal sensor callback."""

    async def test_start_scan_callback_converts_sensor_object(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """start_scan() registers a callback that converts sensor objects and enqueues.

        Technique: Specification-based — the start_scan wrapper is a distinct code
        path from register_callback; both must correctly bridge sensor objects.
        """
        from datetime import datetime

        adapter, mock_instance = opened_adapter

        await adapter.start_scan()

        callback = mock_instance.register_all.call_args[0][0]
        fake_sensor = FakeLaCrosseSensor(
            sensorid=42, temperature=21.5, humidity=55, low_battery=False
        )
        callback(fake_sensor, None)

        reading = await anext(adapter)
        assert reading.sensor_id == 42
        assert reading.temperature == 21.5
        assert reading.humidity == 55
        assert reading.low_battery is False
        assert isinstance(reading.timestamp, datetime)

    async def test_start_scan_callback_drops_sensor_missing_sensorid(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """start_scan() callback logs warning and skips sensor without sensorid.

        Technique: Error Guessing — partial sensor object from hardware.
        """
        adapter, mock_instance = opened_adapter

        await adapter.start_scan()
        callback = mock_instance.register_all.call_args[0][0]

        class BadSensor:
            temperature = 20.0
            humidity = 50
            low_battery = False

        with caplog.at_level(logging.WARNING):
            callback(BadSensor(), None)

        assert "Invalid sensor object - missing sensorid" in caplog.text

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(adapter), timeout=0.1)


# ======================================================================
# Async iterator
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterAsyncIterator:
    """PEP 525 compliance and iterator lifecycle tests."""

    async def test_async_iterator_stops_on_close(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Async iterator raises StopAsyncIteration when adapter is closed.

        Technique: State Transition — iterator termination via sentinel.
        """
        adapter, _ = opened_adapter

        await adapter.start_scan()
        asyncio.create_task(adapter.close())

        with pytest.raises(StopAsyncIteration):
            await anext(adapter)

    async def test_async_iterator_stays_exhausted(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Closed iterator continues to raise StopAsyncIteration (PEP 525 compliance).

        Technique: Error Guessing — verify iterator stays exhausted after close.
        PEP 525 requires that once exhausted, an async iterator must keep raising
        StopAsyncIteration on every subsequent call rather than blocking.
        """
        adapter, _ = opened_adapter

        await adapter.start_scan()
        await adapter.close()

        with pytest.raises(StopAsyncIteration):
            await anext(adapter)

        # Subsequent calls must also raise immediately, not block
        with pytest.raises(StopAsyncIteration):
            await anext(adapter)


# ======================================================================
# Health check
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterHealthCheck:
    """Specification-based tests for health_check serial-port probing."""

    async def test_returns_true_when_port_exists(self, mock_pylacrosse) -> None:
        """health_check returns True when the serial port device file is present.

        Technique: Specification-based — device file accessible → healthy.
        """
        from unittest.mock import patch

        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
        await adapter.open()

        with patch("jeelink2mqtt.adapters.os.path.exists", return_value=True):
            result = await adapter.health_check()

        assert result is True

    async def test_returns_false_when_port_missing(self, mock_pylacrosse) -> None:
        """health_check returns False when the serial port device file is gone.

        Technique: Error Guessing — USB unplug removes device file → unhealthy.
        """
        from unittest.mock import patch

        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
        await adapter.open()

        with patch("jeelink2mqtt.adapters.os.path.exists", return_value=False):
            result = await adapter.health_check()

        assert result is False

    def test_isinstance_health_checkable(self, mock_pylacrosse) -> None:
        """PyLaCrosseAdapter satisfies the HealthCheckable protocol.

        Technique: Specification-based — PEP 544 runtime_checkable check.
        """
        from cosalette import HealthCheckable

        from jeelink2mqtt.adapters import PyLaCrosseAdapter
        from jeelink2mqtt.ports import JeeLinkPort

        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
        assert isinstance(adapter, HealthCheckable)
        assert isinstance(adapter, JeeLinkPort)
