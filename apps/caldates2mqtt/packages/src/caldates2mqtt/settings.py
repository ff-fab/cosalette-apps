"""Application settings for caldates2mqtt.

Extends cosalette's Settings with per-calendar CalDAV configuration.
All settings are loaded from environment variables (CALDATES2MQTT_ prefix),
.env files, or CLI flags. Priority: CLI > env > .env > defaults.
"""

from __future__ import annotations

import cosalette
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import SettingsConfigDict


class CalendarConfig(BaseModel):
    """Configuration for a single CalDAV calendar.

    Each calendar becomes its own MQTT device, identified by ``key``.
    """

    key: str = Field(
        description="Unique identifier, used as MQTT device name and topic segment"
    )
    url: str = Field(description="CalDAV server URL")
    calendar_name: str = Field(description="Calendar name on the server")
    username: str = Field(description="CalDAV auth username")
    password: SecretStr = Field(description="CalDAV auth password")
    entries: int = Field(default=5, description="Number of upcoming events to fetch")
    days: int = Field(default=14, description="Lookahead window in days")
    poll_interval: float = Field(
        default=7200.0,
        gt=0,
        description="Seconds between reads (default 2h)",
    )


class CalDates2MqttSettings(cosalette.Settings):
    """CalDAV calendar date reading settings.

    Extends cosalette base settings with per-calendar CalDAV configuration.
    Calendars are configured as a JSON list in the CALDATES2MQTT_CALENDARS
    environment variable.
    """

    model_config = SettingsConfigDict(
        env_prefix="CALDATES2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    calendars: list[CalendarConfig] = Field(
        min_length=1,
        description="List of calendar configurations (at least one required)",
    )
    caldav_timeout: float = Field(
        default=30.0,
        gt=0,
        description="HTTP timeout for CalDAV requests in seconds",
    )
