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
    so app._telemetry[0] is used instead of the name-based lookup used in
    airthings2mqtt.
    """

    def test_retry_count_is_three(self) -> None:
        """Telemetry registration has retry=3.

        Technique: Specification-based — verify declared retry configuration.
        """
        from caldates2mqtt.main import app

        reg = app._telemetry[0]
        assert reg.retry == 3

    def test_retry_on_includes_caldav_connection_error(self) -> None:
        """retry_on tuple contains CalDavConnectionError.

        Technique: Specification-based — connection failures should be retried.
        """
        from caldates2mqtt.errors import CalDavConnectionError
        from caldates2mqtt.main import app

        reg = app._telemetry[0]
        assert CalDavConnectionError in reg.retry_on

    def test_retry_on_includes_caldav_timeout_error(self) -> None:
        """retry_on tuple contains CalDavTimeoutError.

        Technique: Specification-based — timeout failures should be retried.
        """
        from caldates2mqtt.errors import CalDavTimeoutError
        from caldates2mqtt.main import app

        reg = app._telemetry[0]
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
