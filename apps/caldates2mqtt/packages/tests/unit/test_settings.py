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

    def test_default_schedule(self) -> None:
        """Default schedule is '0 0 0/2 * * ?' (every 2 hours)."""
        settings = make_caldates2mqtt_settings()
        assert settings.calendars[0].schedule == "0 0 0/2 * * ?"

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

    def test_schedule_accepts_valid_cron(self) -> None:
        """Schedule accepts valid Quartz cron expressions."""
        settings = make_caldates2mqtt_settings(
            calendars=[
                {
                    "key": "test",
                    "url": "https://example.com/",
                    "calendar_name": "cal",
                    "username": "u",
                    "password": "p",
                    "schedule": "0 30 9-17 * * MON-FRI",
                }
            ]
        )
        assert settings.calendars[0].schedule == "0 30 9-17 * * MON-FRI"

    def test_entries_rejects_zero(self) -> None:
        """Entries must be > 0."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "entries": 0,
                    }
                ]
            )

    def test_entries_rejects_negative(self) -> None:
        """Negative entries is rejected."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "entries": -1,
                    }
                ]
            )

    def test_days_rejects_zero(self) -> None:
        """Days must be > 0."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "days": 0,
                    }
                ]
            )

    def test_days_rejects_negative(self) -> None:
        """Negative days is rejected."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "days": -1,
                    }
                ]
            )

    def test_caldav_timeout_rejects_zero(self) -> None:
        """CalDAV timeout must be > 0."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(caldav_timeout=0)

    def test_calendars_must_have_at_least_one(self) -> None:
        """Empty calendars list is rejected."""
        with pytest.raises(ValidationError):
            make_caldates2mqtt_settings(calendars=[])

    def test_schedule_rejects_too_few_fields(self) -> None:
        """Schedule with fewer than 6 fields is rejected."""
        with pytest.raises(ValidationError, match="6 or 7"):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "schedule": "* * *",
                    }
                ]
            )

    def test_schedule_rejects_plain_text(self) -> None:
        """A non-cron string like 'every 2 hours' is rejected."""
        with pytest.raises(ValidationError, match="6 or 7"):
            make_caldates2mqtt_settings(
                calendars=[
                    {
                        "key": "test",
                        "url": "https://example.com/",
                        "calendar_name": "cal",
                        "username": "u",
                        "password": "p",
                        "schedule": "every 2 hours",
                    }
                ]
            )

    def test_schedule_accepts_seven_field_cron(self) -> None:
        """Optional 7th year field is accepted."""
        settings = make_caldates2mqtt_settings(
            calendars=[
                {
                    "key": "test",
                    "url": "https://example.com/",
                    "calendar_name": "cal",
                    "username": "u",
                    "password": "p",
                    "schedule": "0 0 12 * * ? 2025-2030",
                }
            ]
        )
        assert settings.calendars[0].schedule == "0 0 12 * * ? 2025-2030"


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
                    "schedule": "0 0 8,20 * * ?",
                }
            ]
        )
        cal = settings.calendars[0]
        assert cal.entries == 3
        assert cal.days == 7
        assert cal.schedule == "0 0 8,20 * * ?"

    def test_password_not_leaked_in_repr(self) -> None:
        """SecretStr password is masked in repr."""
        settings = make_caldates2mqtt_settings()
        repr_str = repr(settings.calendars[0].password)
        assert "testpass" not in repr_str
        assert "**" in repr_str
