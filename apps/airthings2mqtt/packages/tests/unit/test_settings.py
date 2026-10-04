"""Unit tests for airthings2mqtt settings — Airthings2MqttSettings validation.

Test Techniques Used:
- Boundary Value Analysis: Numeric field constraints (ge)
- Equivalence Partitioning: Valid/invalid setting values
- Specification-based: Default values match documentation
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_airthings2mqtt_settings


@pytest.mark.unit
class TestAirthings2MqttSettingsDefaults:
    """Verify default values match documentation."""

    def test_default_device_name(self) -> None:
        """Default device name is 'airthings'."""
        settings = make_airthings2mqtt_settings()
        assert settings.device_name == "airthings"

    def test_default_poll_interval(self) -> None:
        """Default poll interval is 1500 seconds."""
        settings = make_airthings2mqtt_settings()
        assert settings.poll_interval == 1500

    def test_device_mac_required(self) -> None:
        """device_mac has no default — omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(device_mac=None)


@pytest.mark.unit
class TestAirthings2MqttSettingsValidation:
    """Verify field validation constraints.

    Technique: Boundary Value Analysis — test at and beyond boundaries.
    """

    def test_poll_interval_rejects_below_minimum(self) -> None:
        """Poll interval must be >= 60."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_interval=59)

    def test_poll_interval_accepts_minimum(self) -> None:
        """Poll interval of 60 is valid (boundary for ge=60)."""
        settings = make_airthings2mqtt_settings(poll_interval=60)
        assert settings.poll_interval == 60

    def test_poll_interval_rejects_negative(self) -> None:
        """Poll interval must be >= 60."""
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_interval=-1)

    def test_custom_device_name(self) -> None:
        """Custom device name is accepted."""
        settings = make_airthings2mqtt_settings(device_name="wave-bedroom")
        assert settings.device_name == "wave-bedroom"

    def test_custom_device_mac(self) -> None:
        """Custom MAC address is stored."""
        settings = make_airthings2mqtt_settings(device_mac="11:22:33:44:55:66")
        assert settings.device_mac == "11:22:33:44:55:66"

    def test_default_poll_timeout(self) -> None:
        """Default poll timeout is 120.0 seconds.

        Technique: Specification-based — verify the documented default.
        """
        settings = make_airthings2mqtt_settings()
        assert settings.poll_timeout == 120.0

    def test_poll_timeout_accepts_minimum(self) -> None:
        """Poll timeout accepts the 5.0s floor (inclusive boundary).

        Technique: Boundary Value Analysis — minimum valid value at the ge=5.0
        boundary.
        """
        settings = make_airthings2mqtt_settings(poll_timeout=5.0)
        assert settings.poll_timeout == 5.0

    def test_poll_timeout_rejects_below_minimum(self) -> None:
        """Poll timeout just below the 5.0s floor is rejected (e.g. a '1.2' typo).

        Technique: Boundary Value Analysis — just below the ge=5.0 boundary.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_timeout=4.9)

    def test_poll_timeout_rejects_zero(self) -> None:
        """Poll timeout of zero is rejected (below the 5.0s floor).

        Technique: Boundary Value Analysis — zero is well below the minimum.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_timeout=0.0)

    def test_poll_timeout_rejects_negative(self) -> None:
        """Negative poll timeout is rejected.

        Technique: Error Guessing — negative durations are invalid.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(poll_timeout=-1.0)

    def test_poll_timeout_accepts_positive(self) -> None:
        """An interior positive float is a valid poll timeout.

        Technique: Equivalence Partitioning — representative in-range value.
        """
        settings = make_airthings2mqtt_settings(poll_timeout=60.0)
        assert settings.poll_timeout == 60.0

    def test_default_trigger_min_interval(self) -> None:
        """Default trigger throttle is 30.0 seconds .

        Technique: Specification-based — the field default preserves the
        previously hard-coded constant.
        """
        settings = make_airthings2mqtt_settings()
        assert settings.trigger_min_interval == 30.0

    def test_custom_trigger_min_interval(self) -> None:
        """A deployment can raise or lower the throttle.

        Technique: Equivalence Partitioning — representative override.
        """
        settings = make_airthings2mqtt_settings(trigger_min_interval=45.0)
        assert settings.trigger_min_interval == 45.0

    def test_trigger_min_interval_rejects_zero(self) -> None:
        """Zero is rejected (gt=0) — a throttle of nothing is a footgun.

        Technique: Boundary Value Analysis — the excluded lower bound.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(trigger_min_interval=0.0)

    def test_trigger_min_interval_rejects_negative(self) -> None:
        """Negative spacing is rejected.

        Technique: Error Guessing — negative durations are invalid.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(trigger_min_interval=-1.0)

    def test_default_lta_settle_days(self) -> None:
        """The long-term average is provisional for 30 days after a reset."""
        settings = make_airthings2mqtt_settings()
        assert settings.lta_settle_days == 30

    def test_lta_settle_days_accepts_zero(self) -> None:
        """Zero disables the provisional phase.

        Technique: Boundary Value Analysis — the inclusive lower bound.
        """
        settings = make_airthings2mqtt_settings(lta_settle_days=0)
        assert settings.lta_settle_days == 0

    def test_lta_settle_days_rejects_negative(self) -> None:
        """A negative settle period is rejected (ge=0).

        Technique: Boundary Value Analysis — just below the lower bound.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(lta_settle_days=-1)

    def test_default_exit_after_stale_restarts_after_about_six_hours(self) -> None:
        """Stale window plus exit_after_stale is about 6 h with the defaults.

        Technique: Specification-based — docs/configuration.md promises one
        restart about every 6 h for a dead sensor. cosalette counts
        exit_after_stale from the stale transition, and the derived stale_after
        is 2 x poll_interval + 4 x poll_timeout + 3 x 72 s (main.py).
        """
        settings = make_airthings2mqtt_settings()
        stale_after = 2 * settings.poll_interval + 4 * settings.poll_timeout + 3 * 72

        assert settings.exit_after_stale == 18000.0
        assert 5.5 * 3600 < stale_after + settings.exit_after_stale < 6.5 * 3600

    def test_exit_after_stale_accepts_zero(self) -> None:
        """Zero disables the exit on a stale sensor.

        Technique: Boundary Value Analysis — the inclusive lower bound.
        """
        settings = make_airthings2mqtt_settings(exit_after_stale=0)
        assert settings.exit_after_stale == 0

    def test_exit_after_stale_rejects_negative(self) -> None:
        """A negative duration is rejected (ge=0).

        Technique: Boundary Value Analysis — just below the lower bound.
        """
        with pytest.raises(ValidationError):
            make_airthings2mqtt_settings(exit_after_stale=-1)
