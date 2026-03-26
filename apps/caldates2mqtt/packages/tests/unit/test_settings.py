"""Unit tests for caldates2mqtt settings — CalDates2MqttSettings validation.

Test Techniques Used:
- Boundary Value Analysis: Numeric field constraints (gt)
- Equivalence Partitioning: Valid/invalid setting values
- Specification-based: Default values match documentation
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.fixtures.config import make_caldates2mqtt_settings


@pytest.mark.unit
class TestCalDates2MqttSettingsDefaults:
    """Verify default values match documentation."""

    def test_default_entries(self) -> None:
        """Default entries per calendar is 5."""
        settings = make_caldates2mqtt_settings()
        assert settings.calendars[0].entries == 5

    def test_default_days(self) -> None:
        """Default lookahead is 14 days."""
        settings = make_caldates2mqtt_settings()
        assert settings.calendars[0].days == 14

    def test_default_poll_interval(self) -> None:
        """Default poll interval is 7200 seconds (2h)."""
        settings = make_caldates2mqtt_settings()
        assert settings.calendars[0].poll_interval == 7200.0

    def test_default_caldav_timeout(self) -> None:
        """Default CalDAV timeout is 30 seconds."""
        settings = make_caldates2mqtt_settings()
        assert settings.caldav_timeout == 30.0

    def test_calendars_required(self) -> None:
        """calendars has no default — omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(calendars=None)


@pytest.mark.unit
class TestCalDates2MqttSettingsValidation:
    """Verify field validation constraints.

    Technique: Boundary Value Analysis — test at and beyond boundaries.
    """

    def test_poll_interval_rejects_zero(self) -> None:
        """Poll interval must be > 0."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "poll_interval": 0,
                    }
                ]
            )

    def test_poll_interval_rejects_negative(self) -> None:
        """Negative poll interval is rejected."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "poll_interval": -1,
                    }
                ]
            )

    def test_poll_interval_accepts_small_positive(self) -> None:
        """Poll interval of 0.1 is valid (gt=0)."""
        settings = make_caldates2mqtt_settings(
            calendars=[
                {
                    "key": "test",
                    "url": "https://example.com/",
                    "calendar_name": "cal",
                    "username": "u",
                    "password": "p",
                    "poll_interval": 0.1,
                }
            ]
        )
        assert settings.calendars[0].poll_interval == 0.1

    def test_caldav_timeout_rejects_zero(self) -> None:
        """CalDAV timeout must be > 0."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(caldav_timeout=0)

    def test_calendars_must_have_at_least_one(self) -> None:
        """Empty calendars list is rejected."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(calendars=[])


@pytest.mark.unit
class TestCalDates2MqttSettingsMultiCalendar:
    """Verify multi-calendar configuration."""

    def test_multi_calendar_config(self) -> None:
        """Multiple calendars can be configured."""
        settings = make_caldates2mqtt_settings(
            calendars=[
                {
                    "key": "garbage",
                    "url": "https://example.com/dav/",
                    "calendar_name": "abfall",
                    "username": "u1",
                    "password": "p1",
                },
                {
                    "key": "birthday",
                    "url": "https://example.com/dav/",
                    "calendar_name": "birthdays",
                    "username": "u2",
                    "password": "p2",
                    "entries": 10,
                    "days": 30,
                },
            ]
        )
        assert len(settings.calendars) == 2
        assert settings.calendars[0].key == "garbage"
        assert settings.calendars[1].key == "birthday"
        assert settings.calendars[1].entries == 10
        assert settings.calendars[1].days == 30

    def test_per_calendar_overrides(self) -> None:
        """Per-calendar values override defaults."""
        settings = make_caldates2mqtt_settings(
            calendars=[
                {
                    "key": "custom",
                    "url": "https://example.com/",
                    "calendar_name": "cal",
                    "username": "u",
                    "password": "p",
                    "entries": 3,
                    "days": 7,
                    "poll_interval": 3600.0,
                }
            ]
        )
        cal = settings.calendars[0]
        assert cal.entries == 3
        assert cal.days == 7
        assert cal.poll_interval == 3600.0

    def test_password_not_leaked_in_repr(self) -> None:
        """SecretStr password is masked in repr."""
        settings = make_caldates2mqtt_settings()
        repr_str = repr(settings.calendars[0].password)
        assert "testpass" not in repr_str
        assert "**" in repr_str
