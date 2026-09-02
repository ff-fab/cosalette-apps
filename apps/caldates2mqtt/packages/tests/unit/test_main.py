"""Unit tests for caldates2mqtt application-level configuration.

Test Techniques Used:
- Specification-based: Verify declared retry configuration on the telemetry registration
"""

from __future__ import annotations

import pytest


@pytest.mark.unit
class TestTelemetryRetryConfig:
    """Verify retry metadata on the calendar telemetry registration.

    caldates2mqtt uses name=_calendar_map (a callable), not a string constant,
    so app.telemetry_registrations[0] is used instead of the name-based lookup used in
    airthings2mqtt.
    """

    def test_retry_count_is_three(self) -> None:
        """Telemetry registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert reg.retry == 3

    def test_retry_on_includes_caldav_connection_error(self) -> None:
        """retry_on tuple contains CalDavConnectionError.

        Technique: Specification-based — connection failures should be retried.
        """
        from caldates2mqtt.errors import CalDavConnectionError
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert CalDavConnectionError in reg.retry_on

    def test_retry_on_includes_caldav_timeout_error(self) -> None:
        """retry_on tuple contains CalDavTimeoutError.

        Technique: Specification-based — timeout failures should be retried.
        """
        from caldates2mqtt.errors import CalDavTimeoutError
        from caldates2mqtt.main import app

        reg = app.telemetry_registrations[0]
        assert CalDavTimeoutError in reg.retry_on


@pytest.mark.unit
class TestAppVersion:
    """Verify the app reports its package version (not the 0.0.0 default)."""

    def test_app_version_matches_package(self) -> None:
        """App version is stamped from package metadata, not the 0.0.0 default.

        Technique: Cross-reference — guards smoke-test finding A-1 (status/log
        reported version 0.0.0 because version= was never passed to App()).
        """
        from caldates2mqtt import __version__
        from caldates2mqtt.main import app

        assert app.version == __version__
        assert not app.version.startswith("0.0.0")


@pytest.mark.unit
class TestTriggerThrottleRegistration:
    """Guard the ADR-066 throttle declared on the production registration."""

    def test_public_set_topic_is_throttled(self) -> None:
        """The /set trigger carries the declared min_interval.

        Technique: Specification-based — caldates2mqtt/{calendar}/set is a
        public MQTT topic, so an unthrottled trigger lets any client queue one
        CalDAV round-trip per message against a third-party server.
        """
        from caldates2mqtt.main import _TRIGGER_MIN_INTERVAL_SECONDS, app

        reg = app.telemetry_registrations[0]
        assert reg.min_interval == _TRIGGER_MIN_INTERVAL_SECONDS

    def test_throttle_is_still_triggerable(self) -> None:
        """min_interval= throttles the trigger, it does not disable it.

        Technique: Specification-based — the throttle requires triggerable=.
        """
        from caldates2mqtt.main import app

        assert app.telemetry_registrations[0].triggerable is not None

    def test_schedule_is_untouched_by_the_throttle(self) -> None:
        """The cron schedule still drives its own cadence.

        Technique: Specification-based — min_interval bounds trigger-initiated
        runs only; a scheduled fire is not a trigger and is never throttled.
        """
        from caldates2mqtt.main import app

        assert app.telemetry_registrations[0].schedule_spec is not None
