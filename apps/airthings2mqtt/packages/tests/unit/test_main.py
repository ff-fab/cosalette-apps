"""Unit tests for airthings2mqtt main — telemetry handler and poll interval.

Test Techniques Used:
- Specification-based: Handler returns correct sensor dict from reader
- Error Guessing: BLE errors propagate through handler (not swallowed)
- Equivalence Partitioning: Duplicate readings are not deduplicated
"""

from __future__ import annotations

import pytest

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError
from airthings2mqtt.ports import AirthingsReading
from tests.fixtures.config import make_airthings2mqtt_settings


@pytest.mark.unit
class TestTelemetryHandler:
    """Verify _telemetry returns correct sensor dict from reader."""

    async def test_returns_sensor_values_from_reading(self) -> None:
        """Handler returns dict with temperature, humidity, radon values from reader.

        Technique: Specification-based — verify contract between handler and reader.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reading = AirthingsReading(
            temperature=19.3,
            humidity=52.0,
            radon_24h_avg=95,
            radon_long_term_avg=72,
        )
        reader = FakeAirthingsReader()
        reader.readings = [reading]
        settings = make_airthings2mqtt_settings()

        # Act
        result = await _telemetry(reader=reader, settings=settings)

        # Assert
        assert result == {
            "temperature": 19.3,
            "humidity": 52.0,
            "radon_24h_avg": 95,
            "radon_long_term_avg": 72,
        }

    async def test_passes_device_mac_to_reader(self) -> None:
        """Handler passes the device_mac from settings to the reader.

        Technique: Specification-based — verify wiring between settings and reader.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        settings = make_airthings2mqtt_settings(device_mac="11:22:33:44:55:66")

        # Act
        await _telemetry(reader=reader, settings=settings)

        # Assert
        assert reader.calls == ["11:22:33:44:55:66"]


@pytest.mark.unit
class TestTelemetryHandlerErrorPropagation:
    """Verify BLE errors propagate through the handler (not swallowed)."""

    async def test_ble_error_propagates(self) -> None:
        """BleConnectionError from reader propagates to caller.

        Technique: Error Guessing — handler must not silently swallow BLE errors.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        reader.raise_on_next = BleConnectionError("device unreachable")
        settings = make_airthings2mqtt_settings()

        # Act & Assert
        with pytest.raises(BleConnectionError, match="device unreachable"):
            await _telemetry(reader=reader, settings=settings)


@pytest.mark.unit
class TestTelemetryDuplicateReadings:
    """Verify handler does not perform client-side deduplication."""

    async def test_duplicate_readings_still_returned(self) -> None:
        """Calling handler twice with same reading returns same dict both times.

        Technique: Equivalence Partitioning — duplicate readings are valid.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reading = AirthingsReading(
            temperature=21.5,
            humidity=45.0,
            radon_24h_avg=80,
            radon_long_term_avg=65,
        )
        reader = FakeAirthingsReader()
        reader.readings = [reading]
        settings = make_airthings2mqtt_settings()
        expected = {
            "temperature": 21.5,
            "humidity": 45.0,
            "radon_24h_avg": 80,
            "radon_long_term_avg": 65,
        }

        # Act
        first = await _telemetry(reader=reader, settings=settings)
        second = await _telemetry(reader=reader, settings=settings)

        # Assert
        assert first == expected
        assert second == expected


@pytest.mark.unit
class TestPollInterval:
    """Verify deferred poll interval resolution from settings."""

    def test_poll_interval_resolves_from_settings(self) -> None:
        """_poll_interval returns float of settings.poll_interval.

        Technique: Specification-based — verify deferred interval contract.
        """
        from airthings2mqtt.main import _poll_interval

        # Arrange
        settings = make_airthings2mqtt_settings(poll_interval=300)

        # Act
        result = _poll_interval(settings)

        # Assert
        assert result == 300.0
        assert isinstance(result, float)
