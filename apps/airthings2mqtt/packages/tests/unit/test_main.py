"""Unit tests for airthings2mqtt main — telemetry handler and poll interval.

Test Techniques Used:
- Specification-based: Handler returns the reader's AirthingsReading; retry metadata
  matches declared configuration; no adapter auto-restart is configured
- Error Guessing: BLE errors propagate through handler (not swallowed)
- Equivalence Partitioning: Duplicate readings are not deduplicated
- Branch Coverage: Scheduled and triggered telemetry paths (caplog assertions)
- State Transition: Sensor reset tracked across a simulated restart
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import cosalette
import pytest
from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from airthings2mqtt.adapters.fake import FakeAirthingsReader
from airthings2mqtt.errors import BleConnectionError
from airthings2mqtt.ports import AirthingsReading
from tests.fixtures.config import make_airthings2mqtt_settings


def _telemetry_registration() -> object:
    """Return the unexpanded settings-derived telemetry registration."""
    from airthings2mqtt.main import _telemetry, app

    return next(r for r in app.telemetry_registrations if r.func is _telemetry)


def _device_store(backend: MemoryStore | None = None) -> DeviceStore:
    """Return a loaded device store, as the framework injects it."""
    store = DeviceStore(backend or MemoryStore(), "airthings")
    store.load()
    return store


@pytest.mark.unit
class TestTelemetryHandler:
    """Verify _telemetry returns the reading from the reader."""

    async def test_returns_sensor_values_from_reading(self) -> None:
        """Handler returns the AirthingsReading produced by the reader.

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
            store=_device_store(),
        )

        # Assert
        assert result == reading

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
            store=_device_store(),
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
                store=_device_store(),
            )


@pytest.mark.unit
class TestTelemetryDuplicateReadings:
    """Verify handler does not perform client-side deduplication."""

    async def test_duplicate_readings_still_returned(self) -> None:
        """Calling handler twice with same reading returns it both times.

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
        expected = reading

        # Act
        first = await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
            store=_device_store(),
        )
        second = await _telemetry(
            reader=reader,
            settings=settings,
            trigger=trigger,
            logger=logger,
            store=_device_store(),
        )

        # Assert
        assert first == expected
        assert second == expected


@pytest.mark.unit
class TestTelemetrySensorReset:
    """The handler runs readings through the reset tracker (ADR-004)."""

    async def test_reset_is_logged_once_and_survives_a_restart(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A reset logs one INFO line, persists, and is not re-reported.

        Technique: State Transition — normal -> reset -> restart -> warming_up,
        with a fresh DeviceStore over the same backend standing in for a
        container restart (proposal criteria 1, 2 and 6).
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        reader.readings = [
            AirthingsReading(
                temperature=31.6,
                humidity=33.5,
                radon_24h_avg=127,
                radon_long_term_avg=113,
            ),
            AirthingsReading(
                temperature=31.0, humidity=43.5, radon_24h_avg=0, radon_long_term_avg=0
            ),
        ]
        backend = MemoryStore()
        kwargs = {
            "reader": reader,
            "settings": make_airthings2mqtt_settings(),
            "trigger": cosalette.TriggerPayload.scheduled(),
            "logger": logging.getLogger(__name__),
        }

        # Act
        store = _device_store(backend)
        await _telemetry(**kwargs, store=store)
        with caplog.at_level(logging.INFO):
            reset = await _telemetry(**kwargs, store=store)
        store.save()
        restarted = _device_store(backend)
        reader.readings = [reader.readings[1]]
        caplog.clear()
        with caplog.at_level(logging.INFO):
            again = await _telemetry(**kwargs, store=restarted)

        # Assert
        assert reset.radon_24h_avg is None
        assert reset.measurement_state == "warming_up"
        assert again.measurement_state == "warming_up"
        assert again.sensor_reset_at == reset.sensor_reset_at
        assert restarted["reset_tracker"]["lta_before_reset"] == 113
        assert restarted["reset_tracker"]["reset_count"] == 1
        assert "reset detected" not in caplog.text

    async def test_reset_log_names_the_lost_long_term_average(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The INFO line carries the long-term average the reset wiped.

        Technique: Specification-based — operator-facing log contract.
        """
        from airthings2mqtt.main import _telemetry

        # Arrange
        reader = FakeAirthingsReader()
        reader.readings = [
            AirthingsReading(
                temperature=31.0, humidity=43.5, radon_24h_avg=0, radon_long_term_avg=0
            )
        ]
        store = _device_store()
        store["reset_tracker"] = {"last_lta": 113}

        # Act
        with caplog.at_level(logging.INFO):
            await _telemetry(
                reader=reader,
                settings=make_airthings2mqtt_settings(),
                trigger=cosalette.TriggerPayload.scheduled(),
                logger=logging.getLogger(__name__),
                store=store,
            )

        # Assert
        assert "sensor reset detected" in caplog.text
        assert "long-term average 113 -> 0" in caplog.text


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
                store=_device_store(),
            )

        # Assert
        assert reader.calls == ["11:22:33:44:55:66"]
        assert result.temperature == 21.5
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
                store=_device_store(),
            )

        # Assert
        assert reader.calls == ["11:22:33:44:55:66"]
        assert result.temperature == 21.5
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
            _telemetry(
                reader=reader,
                settings=settings,
                trigger=trigger,
                logger=logger,
                store=_device_store(),
            )
        )
        t2 = asyncio.create_task(
            _telemetry(
                reader=reader,
                settings=settings,
                trigger=trigger,
                logger=logger,
                store=_device_store(),
            )
        )

        # Wait for the first task to enter reader.read and block on the gate.
        # At this point t2 must be waiting for the lock — not inside reader.read.
        await asyncio.wait_for(inside_read.wait(), timeout=1.0)
        assert max_active_reads == 1, "Lock must prevent a second concurrent read"

        # Release the gate; both tasks complete serially.
        gate.set()
        r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)

        assert max_active_reads == 1
        assert r1.temperature == 21.5
        assert r2.temperature == 21.5


@pytest.mark.unit
class TestTelemetryRetryConfig:
    """Verify retry metadata on the airthings telemetry registration."""

    def test_retry_count_is_three(self) -> None:
        """Telemetry registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        reg = _telemetry_registration()
        assert reg.retry == 3

    def test_retry_on_includes_ble_connection_error(self) -> None:
        """retry_on tuple contains BleConnectionError.

        Technique: Specification-based — connection failures should be retried.
        """
        from airthings2mqtt.errors import BleConnectionError

        reg = _telemetry_registration()
        assert BleConnectionError in reg.retry_on

    def test_retry_on_includes_ble_timeout_error(self) -> None:
        """retry_on tuple contains BleTimeoutError.

        Technique: Specification-based — timeout failures should be retried.
        """
        from airthings2mqtt.errors import BleTimeoutError

        reg = _telemetry_registration()
        assert BleTimeoutError in reg.retry_on

    def test_retry_on_includes_framework_timeout_error(self) -> None:
        """retry_on tuple contains TimeoutError for cosalette F-3 auto-timeout.

        Technique: Specification-based — framework-injected TimeoutError from
        asyncio.wait_for must self-heal via the retry mechanism.
        """
        reg = _telemetry_registration()
        assert TimeoutError in reg.retry_on

    def test_unavailable_on_adds_read_error_to_retry_on(self) -> None:
        """Every terminal failure marks the device offline, retried or not.

        Technique: Specification-based — a persistent non-retryable
        BleReadError must not leave a stale reading looking online.
        """
        from airthings2mqtt.errors import BleReadError

        reg = _telemetry_registration()
        assert reg.unavailable_on == (*reg.retry_on, BleReadError)

    def test_timeout_configured_from_poll_timeout_setting(self) -> None:
        """Telemetry timeout= resolves via setting_ref("poll_timeout").

        Technique: Specification-based — timeout must be a SettingRef bound
        to poll_timeout so the framework applies the per-poll budget.
        """
        reg = _telemetry_registration()
        assert reg.timeout is not None
        assert reg.timeout.field_name == "poll_timeout"


@pytest.mark.unit
class TestMakeReader:
    """Verify the production reader's scan stays inside the poll budget."""

    @pytest.mark.parametrize(
        ("poll_timeout", "scan_timeout"), [(120.0, 10.0), (40.0, 10.0), (20.0, 5.0)]
    )
    def test_scan_timeout_bounded_by_poll_timeout(
        self, poll_timeout: float, scan_timeout: float
    ) -> None:
        """Scan gets a quarter of poll_timeout, capped at bleak's 10 s default.

        Technique: Boundary Value Analysis — at, above and below the cap.
        """
        from airthings2mqtt.main import _make_reader

        settings = make_airthings2mqtt_settings(
            device_mac="AA:BB:CC:DD:EE:FF", poll_timeout=poll_timeout
        )

        assert _make_reader(settings)._scan_timeout == scan_timeout


@pytest.mark.unit
class TestAppRestartConfig:
    """Verify the app does not configure adapter auto-restart (ADR-003)."""

    def test_bleak_reader_opts_out_of_restart(self) -> None:
        """BleakAirthingsReader declares restartable = False.

        Technique: Specification-based — cosalette skips opted-out adapters.
        """
        from airthings2mqtt.adapters.bleak import BleakAirthingsReader

        assert BleakAirthingsReader.restartable is False


@pytest.mark.unit
class TestLogRedaction:
    """Verify the app scrubs sensor MACs from everything it logs (ADR-085)."""

    def test_app_redacts_mac_addresses(self) -> None:
        """App(redact=) masks a BlueZ object-path MAC down to its last octets.

        Technique: Specification-based — bleak/BlueZ log records embed the
        address outside the adapter's own error-text redaction.
        """
        from airthings2mqtt.main import app

        assert app._redactor is not None
        assert app._redactor("/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF") == (
            "/org/bluez/hci0/dev_**:EE:FF"
        )


@pytest.mark.unit
class TestHealthProbeEntryPoint:
    """Verify the console entry point exposes the container probe (ADR-083)."""

    def test_health_subcommand_fails_on_missing_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """``airthings2mqtt health`` runs the probe instead of starting the app.

        Technique: Specification-based — the Dockerfile HEALTHCHECK calls this
        subcommand; a missing health file must exit 1 (unhealthy).
        """
        from airthings2mqtt.main import main

        missing = tmp_path / "health.json"
        monkeypatch.setattr(
            sys, "argv", ["airthings2mqtt", "health", "--file", str(missing)]
        )

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


@pytest.mark.unit
class TestAppVersion:
    """Verify the app reports its package version (not the 0.0.0 default)."""

    def test_app_version_matches_package(self) -> None:
        """App version is stamped from package metadata, not the 0.0.0 default.

        Technique: Cross-reference — guards smoke-test finding A-1 (status/log
        reported version 0.0.0 because version= was never passed to App()).
        """
        from airthings2mqtt import __version__
        from airthings2mqtt.main import app

        assert app.version == __version__
        assert not app.version.startswith("0.0.0")


@pytest.mark.unit
class TestTriggerThrottleRegistration:
    """Guard the ADR-066 throttle declared on the production registration."""

    def _registration(self) -> object:
        return _telemetry_registration()

    def test_public_set_topic_is_throttled(self) -> None:
        """The /set trigger carries the declared min_interval.

        Technique: Specification-based — airthings2mqtt/airthings/set is a
        public MQTT topic, so an unthrottled trigger lets any client queue one
        BLE round-trip per message.
        """
        from airthings2mqtt.main import _TRIGGER_MIN_INTERVAL_SECONDS

        assert self._registration().min_interval == _TRIGGER_MIN_INTERVAL_SECONDS

    def test_throttle_is_still_triggerable(self) -> None:
        """min_interval= throttles the trigger, it does not disable it.

        Technique: Specification-based — the throttle requires triggerable=.
        """
        assert self._registration().triggerable is not None

    def test_throttle_cannot_slow_the_scheduled_poll(self) -> None:
        """The throttle stays well below the minimum allowed poll interval.

        Technique: Boundary Value Analysis — a min_interval above the scheduled
        cadence would start delaying ordinary polls, not just trigger storms.
        """
        from airthings2mqtt.main import _TRIGGER_MIN_INTERVAL_SECONDS

        min_poll_interval = 60.0  # Airthings2MqttSettings.poll_interval ge=60
        assert min_poll_interval > _TRIGGER_MIN_INTERVAL_SECONDS

    def test_config_file_override_updates_the_throttle(self, tmp_path: Path) -> None:
        """A CLI-selected config file flows into the throttle before startup.

        Technique: Regression — CLI config is loaded after module import, so
        registration-time settings would silently leave the default throttle.
        """
        from airthings2mqtt.main import _configure_trigger_min_interval
        from airthings2mqtt.settings import Airthings2MqttSettings

        config_file = tmp_path / "settings.json"
        config_file.write_text(
            '{"device_mac":"AA:BB:CC:DD:EE:FF","trigger_min_interval":300}',
            encoding="utf-8",
        )
        settings = Airthings2MqttSettings(_config_file=config_file)

        _configure_trigger_min_interval(settings)
        try:
            assert self._registration().min_interval == 300.0
        finally:
            _configure_trigger_min_interval(
                Airthings2MqttSettings(device_mac="AA:BB:CC:DD:EE:FF")
            )

    def test_registration_starts_with_the_default_throttle(self) -> None:
        """The default remains available until CLI settings load.

        Technique: Specification-based — ``--help`` and schema generation may
        import the module without resolving runtime settings.
        """
        from airthings2mqtt.main import _TRIGGER_MIN_INTERVAL_SECONDS

        assert self._registration().min_interval == _TRIGGER_MIN_INTERVAL_SECONDS
