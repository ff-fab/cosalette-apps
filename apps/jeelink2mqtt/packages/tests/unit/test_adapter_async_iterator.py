"""Tests for PyLaCrosseAdapter async iterator functionality and new callback shape.

These tests focus on the pylacrosse 0.4 changes:
- Callback receives sensor objects instead of strings
- Async iterator functionality works correctly
- Error handling for malformed sensor objects
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch
from datetime import UTC, datetime

import pytest

from jeelink2mqtt.models import SensorReading


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
    """Mock pylacrosse module injected into ``sys.modules``."""
    mock_module = MagicMock()
    mock_instance = MagicMock()
    mock_module.LaCrosse.return_value = mock_instance
    with patch.dict("sys.modules", {"pylacrosse": mock_module}):
        yield mock_module, mock_instance


@pytest.fixture()
async def opened_adapter(mock_pylacrosse):
    """PyLaCrosseAdapter that has already been open()ed."""
    from jeelink2mqtt.adapters import PyLaCrosseAdapter

    _, mock_instance = mock_pylacrosse
    adapter = PyLaCrosseAdapter(port="/dev/ttyUSB0", baud_rate=57600)
    await adapter.open()
    mock_instance.reset_mock()  # Clear the open() call
    return adapter, mock_instance


@pytest.mark.unit
class TestPyLaCrosseAdapterAsyncIterator:
    """Tests for async iterator functionality with pylacrosse 0.4 sensor objects."""

    async def test_start_scan_callback_accepts_sensor_object(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """start_scan() registers callback that accepts (sensor, user_data) and enqueues SensorReading."""
        adapter, mock_instance = opened_adapter

        # Act - start scanning which registers a callback
        await adapter.start_scan()

        # Assert callback was registered with register_all
        mock_instance.register_all.assert_called_once()

        # Get the registered callback
        callback = mock_instance.register_all.call_args[0][0]

        # Create fake sensor object
        fake_sensor = FakeLaCrosseSensor(
            sensorid=42, temperature=21.5, humidity=55, low_battery=False
        )

        # Call the callback as pylacrosse 0.4 would
        callback(fake_sensor, None)

        # Verify the reading was enqueued by checking async iterator
        reading = await anext(adapter)

        assert reading.sensor_id == 42
        assert reading.temperature == 21.5
        assert reading.humidity == 55
        assert reading.low_battery is False
        assert isinstance(reading.timestamp, datetime)

    async def test_start_scan_callback_handles_bad_sensor_attributes(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """start_scan() callback logs warnings for sensor objects missing expected attributes."""
        adapter, mock_instance = opened_adapter

        await adapter.start_scan()
        callback = mock_instance.register_all.call_args[0][0]

        # Create sensor missing sensorid attribute
        class BadSensor:
            temperature = 20.0
            humidity = 50
            low_battery = False

        # Call callback with bad sensor
        with caplog.at_level(logging.WARNING):
            callback(BadSensor(), None)

        # Assert warning was logged and no reading enqueued
        assert "Invalid sensor object - missing sensorid" in caplog.text

        # Verify no reading was enqueued (should timeout quickly)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(anext(adapter), timeout=0.1)

    async def test_register_callback_accepts_sensor_object(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """register_callback() now accepts sensor objects instead of strings."""
        adapter, mock_instance = opened_adapter

        # Arrange
        received: list[SensorReading] = []
        adapter.register_callback(received.append)

        # Get the wrapper that was passed to register_all
        callback = mock_instance.register_all.call_args[0][0]

        # Create fake sensor object
        fake_sensor = FakeLaCrosseSensor(
            sensorid=123, temperature=-5.2, humidity=85, low_battery=True
        )

        # Act - call as pylacrosse 0.4 would
        callback(fake_sensor, None)

        # Assert
        assert len(received) == 1
        reading = received[0]
        assert reading.sensor_id == 123
        assert reading.temperature == -5.2
        assert reading.humidity == 85
        assert reading.low_battery is True

    async def test_register_callback_handles_attribute_error(
        self, opened_adapter: tuple[object, MagicMock], caplog
    ) -> None:
        """register_callback() logs AttributeError for malformed sensor objects."""
        adapter, mock_instance = opened_adapter

        received: list[SensorReading] = []
        adapter.register_callback(received.append)
        callback = mock_instance.register_all.call_args[0][0]

        # Create sensor missing humidity attribute
        class IncompleteeSensor:
            sensorid = 99
            temperature = 25.0
            # missing humidity
            low_battery = False

        # Act
        with caplog.at_level(logging.WARNING):
            callback(IncompleteeSensor(), None)

        # Assert
        assert "Sensor missing expected attribute" in caplog.text
        assert len(received) == 0  # No reading should be generated

    async def test_async_iterator_stops_on_close(
        self, opened_adapter: tuple[object, MagicMock]
    ) -> None:
        """Async iterator raises StopAsyncIteration when adapter is closed."""
        adapter, _ = opened_adapter

        # Start scanning so we can iterate
        await adapter.start_scan()

        # Close adapter in background to signal termination
        asyncio.create_task(adapter.close())

        # Verify iteration terminates
        with pytest.raises(StopAsyncIteration):
            await anext(adapter)


@pytest.mark.unit
class TestFakeJeeLinkAdapterReopen:
    """Tests for FakeJeeLinkAdapter reopen semantics."""

    async def test_reopen_clears_queue_state(self) -> None:
        """open() after close() clears queue to prevent stale readings."""
        from jeelink2mqtt.adapters import FakeJeeLinkAdapter
        from jeelink2mqtt.models import SensorReading
        from datetime import datetime

        adapter = FakeJeeLinkAdapter()

        # First session: open -> inject -> close
        await adapter.open()
        test_reading = SensorReading(
            sensor_id=99,
            temperature=25.0,
            humidity=60,
            low_battery=False,
            timestamp=datetime.now(UTC),
        )
        adapter.inject_async(test_reading)
        await adapter.close()

        # Second session: reopen -> inject new reading
        await adapter.open()
        new_reading = SensorReading(
            sensor_id=100,
            temperature=30.0,
            humidity=50,
            low_battery=True,
            timestamp=datetime.now(UTC),
        )
        adapter.inject_async(new_reading)

        # Should get the new reading, not StopAsyncIteration from close sentinel
        reading = await anext(adapter)
        assert reading.sensor_id == 100
        assert reading.temperature == 30.0
