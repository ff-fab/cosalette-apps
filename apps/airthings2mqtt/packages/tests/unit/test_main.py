"""Unit tests for airthings2mqtt main — telemetry handler and poll interval.

Test Techniques Used:
- Specification-based: Handler returns correct sensor dict from reader; retry and
  restart metadata matches declared configuration
- Error Guessing: BLE errors propagate through handler (not swallowed)
- Equivalence Partitioning: Duplicate readings are not deduplicated
- Branch Coverage: Scheduled and triggered telemetry paths (caplog assertions)
"""

from __future__ import annotations

import asyncio
import logging

import cosalette
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
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger(__name__)

        # Act
        result = await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
        )

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
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger(__name__)

        # Act
        await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
        )

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
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger(__name__)

        # Act & Assert
        with pytest.raises(BleConnectionError, match="device unreachable"):
            await _telemetry(
                reader=reader,
                settings=settings,
                trigger=trigger,
                logger=logger,
            )


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
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger(__name__)
        expected = {
            "temperature": 21.5,
            "humidity": 45.0,
            "radon_24h_avg": 80,
            "radon_long_term_avg": 65,
        }

        # Act
        first = await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
        )
        second = await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
        )

        # Assert
        assert first == expected
        assert second == expected


@pytest.mark.unit
class TestTelemetryTrigger:
    """Verify on-demand trigger path reads the sensor immediately."""

    async def test_triggered_payload_rereads_sensor(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Triggered telemetry performs a normal sensor read and logs intent.

        Technique: Branch Coverage — exercise TriggerPayload.is_triggered=True.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        settings = make_airthings2mqtt_settings(device_mac="11:22:33:44:55:66")
        trigger = cosalette.TriggerPayload.from_mqtt("")
        logger = logging.getLogger("tests.airthings2mqtt.trigger")

        # Act
        with caplog.at_level(logging.INFO, logger=logger.name):
            result = await _telemetry(
                reader=reader,
                settings=settings,
                trigger=trigger,
                logger=logger,
            )

        # Assert
        assert reader.calls == ["11:22:33:44:55:66"]
        assert result["temperature"] == 21.5
        assert "On-demand Airthings re-read triggered" in caplog.messages

    async def test_scheduled_payload_does_not_log_trigger(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Scheduled telemetry returns sensor data without logging trigger intent.

        Technique: Branch Coverage — scheduled path does not enter the
        ``trigger.is_triggered`` branch; caplog must stay silent.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        settings = make_airthings2mqtt_settings(device_mac="11:22:33:44:55:66")
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger("tests.airthings2mqtt.trigger")

        # Act
        with caplog.at_level(logging.INFO, logger=logger.name):
            result = await _telemetry(
                reader=reader,
                settings=settings,
                trigger=trigger,
                logger=logger,
            )

        # Assert
        assert reader.calls == ["11:22:33:44:55:66"]
        assert result["temperature"] == 21.5
        assert "On-demand Airthings re-read triggered" not in caplog.messages


@pytest.mark.unit
class TestReadLockSerialization:
    """Verify _get_read_lock serializes concurrent telemetry reads."""

    async def test_concurrent_reads_are_serialized(self) -> None:
        """Two concurrent _telemetry calls never overlap inside reader.read.

        Technique: Concurrency — prove the per-loop lock prevents simultaneous
        reader.read invocations.  A controlled reader gates each call behind an
        asyncio.Event so we can observe the concurrency counter mid-flight.
        """
        from airthings2mqtt.main import _telemetry

        active_reads = 0
        max_active_reads = 0
        inside_read = asyncio.Event()
        gate = asyncio.Event()
        reading = AirthingsReading(
            temperature=21.5, humidity=45.0, radon_24h_avg=80, radon_long_term_avg=65
        )

        class _CountingReader:
            async def read(self, _mac: str) -> AirthingsReading:
                nonlocal active_reads, max_active_reads
                active_reads += 1
                max_active_reads = max(max_active_reads, active_reads)
                inside_read.set()  # signal: I am inside read, blocked on gate
                await gate.wait()
                active_reads -= 1
                return reading

        reader = _CountingReader()
        settings = make_airthings2mqtt_settings()
        trigger = cosalette.TriggerPayload.scheduled()
        logger = logging.getLogger(__name__)

        t1 = asyncio.create_task(
            _telemetry(reader=reader, settings=settings, trigger=trigger, logger=logger)
        )
        t2 = asyncio.create_task(
            _telemetry(reader=reader, settings=settings, trigger=trigger, logger=logger)
        )

        # Wait for the first task to enter reader.read and block on the gate.
        # At this point t2 must be waiting for the lock — not inside reader.read.
        await asyncio.wait_for(inside_read.wait(), timeout=1.0)
        assert max_active_reads == 1, "Lock must prevent a second concurrent read"

        # Release the gate; both tasks complete serially.
        gate.set()
        r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)

        assert max_active_reads == 1
        assert r1["temperature"] == 21.5
        assert r2["temperature"] == 21.5


@pytest.mark.unit
class TestTelemetryRetryConfig:
    """Verify retry metadata on the airthings telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """Telemetry registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from airthings2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "airthings")
        assert reg.retry == 3

    def test_retry_on_includes_ble_connection_error(self) -> None:
        """retry_on tuple contains BleConnectionError.

        Technique: Specification-based — connection failures should be retried.
        """
        from airthings2mqtt.errors import BleConnectionError
        from airthings2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "airthings")
        assert BleConnectionError in reg.retry_on

    def test_retry_on_includes_ble_timeout_error(self) -> None:
        """retry_on tuple contains BleTimeoutError.

        Technique: Specification-based — timeout failures should be retried.
        """
        from airthings2mqtt.errors import BleTimeoutError
        from airthings2mqtt.main import app

        reg = next(r for r in app._telemetry if r.name == "airthings")
        assert BleTimeoutError in reg.retry_on


@pytest.mark.unit
class TestAppRestartConfig:
    """Verify restart configuration on the App instance."""

    def test_restart_after_failures_is_five(self) -> None:
        """App is configured to restart after 5 consecutive failures.

        Technique: Specification-based — BLE adapter recovery configuration.
        """
        from airthings2mqtt.main import app

        assert app._restart_after_failures == 5

    def test_max_restarts_is_three(self) -> None:
        """App allows at most 3 restarts before giving up.

        Technique: Specification-based — bounded restart loop prevents runaway.
        """
        from airthings2mqtt.main import app

        assert app._max_restarts == 3
