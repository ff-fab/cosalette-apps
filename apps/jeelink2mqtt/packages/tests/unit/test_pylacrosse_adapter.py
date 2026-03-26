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
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from jeelink2mqtt.models import SensorReading

# ======================================================================
# Fixtures
# ======================================================================


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
def opened_adapter(mock_pylacrosse):
    """PyLaCrosseAdapter that has already been ``open()``-ed.

    Returns ``(adapter, mock_instance)`` with the mock's initial
    ``open()`` call cleared via ``reset_mock()``.
    """
    from jeelink2mqtt.adapters import PyLaCrosseAdapter

    _, mock_instance = mock_pylacrosse
    adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
    adapter.open()
    mock_instance.reset_mock()  # Clear the open() call
    return adapter, mock_instance


# ======================================================================
# Lifecycle: open / close
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterLifecycle:
    """State Transition Testing for open/close lifecycle."""

    def test_open_imports_and_creates_lacrosse(
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
        adapter.open()

        # Assert
        mock_module.LaCrosse.assert_called_once_with("/dev/ttyUSB0", 57600)
        mock_instance.open.assert_called_once()

    def test_close_closes_and_clears(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """close() delegates to the underlying instance and sets it to None.

        Technique: State Transition — open → close nullifies internal state.
        """
        adapter, mock_instance = opened_adapter

        # Act
        adapter.close()

        # Assert
        mock_instance.close.assert_called_once()
        assert adapter._lacrosse is None  # noqa: SLF001

    def test_close_when_not_open_is_noop(self, mock_pylacrosse) -> None:
        """close() on a never-opened adapter is a safe no-op.

        Technique: Error Guessing — calling close before open should
        not raise.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert — no exception
        adapter.close()


# ======================================================================
# Scanning
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterScanning:
    """State Transition Testing for start_scan / stop_scan."""

    def test_start_scan_delegates(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """start_scan() delegates to the underlying pylacrosse instance.

        Technique: Specification-based — verifying delegation contract.
        """
        adapter, mock_instance = opened_adapter

        # Act
        adapter.start_scan()

        # Assert
        mock_instance.start_scan.assert_called_once()

    def test_start_scan_without_open_raises(self, mock_pylacrosse) -> None:
        """start_scan() before open() raises RuntimeError.

        Technique: Error Guessing — precondition violation.
        """
        from jeelink2mqtt.adapters import PyLaCrosseAdapter

        # Arrange
        adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)

        # Act / Assert
        with pytest.raises(RuntimeError, match="Adapter not open"):
            adapter.start_scan()

    def test_stop_scan_does_not_raise(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """stop_scan() is a no-op that logs a debug message.

        Technique: Specification-based — documented no-op behaviour.
        """
        adapter, _ = opened_adapter

        # Act / Assert — no exception raised
        adapter.stop_scan()


# ======================================================================
# Callback registration and frame parsing
# ======================================================================


@pytest.mark.unit
class TestPyLaCrosseAdapterCallback:
    """Branch/Condition Coverage for register_callback and its wrapper."""

    def test_register_callback_wraps_frame(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Valid pylacrosse frame string is parsed into a SensorReading.

        Technique: Specification-based — happy-path frame parsing.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)

        # Get the wrapper that was passed to register_all
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act — simulate pylacrosse calling the wrapper
        wrapper("id=42 t=21.5 h=55 nbat=0")

        # Assert
        assert len(received) == 1
        reading = received[0]
        assert reading.sensor_id == 42
        assert reading.temperature == 21.5
        assert reading.humidity == 55
        assert reading.low_battery is False

    def test_register_callback_parses_low_battery(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """nbat=1 is parsed as low_battery=True.

        Technique: Boundary Value Analysis — boolean boundary (0 vs nonzero).
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        wrapper("id=10 t=18.0 h=70 nbat=1")

        # Assert
        assert len(received) == 1
        assert received[0].low_battery is True

    def test_register_callback_parses_negative_temperature(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Negative temperature is correctly parsed.

        Technique: Boundary Value Analysis — sign change boundary.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        wrapper("id=7 t=-3.2 h=90 nbat=0")

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

    def test_register_callback_ignores_unparsable_frame(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """Wrapper logs a warning and skips when frame doesn't match regex.

        Technique: Error Guessing — malformed input from hardware.
        """
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act
        with caplog.at_level(logging.WARNING):
            wrapper("garbage data here")

        # Assert — callback was NOT invoked
        assert len(received) == 0
        assert "Unparsable LaCrosse frame" in caplog.text

    def test_register_callback_logs_exception_from_callback(
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
        wrapper = mock_instance.register_all.call_args[0][0]

        # Act — exception does NOT propagate
        with caplog.at_level(logging.ERROR):
            wrapper("id=1 t=20.0 h=50 nbat=0")

        # Assert — error is logged
        assert "Error processing LaCrosse frame" in caplog.text


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
