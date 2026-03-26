"""Configuration test fixtures.

Provides fixtures for testing CalDates2MqttSettings.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_settings import PydanticBaseSettingsSource

from caldates2mqtt.settings import CalDates2MqttSettings


class _IsolatedCalDates2MqttSettings(CalDates2MqttSettings):
    """CalDates2MqttSettings subclass that ignores ambient configuration.

    Overrides settings_customise_sources to use only init_settings,
    stripping env vars, .env files, and secrets. This ensures tests
    are fully deterministic regardless of the host environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[CalDates2MqttSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


_DEFAULT_CALENDAR = {
    "key": "garbage",
    "url": "https://cloud.example.com/remote.php/dav/calendars/user/",
    "calendar_name": "abfall_shared_by_fab",
    "username": "testuser",
    "password": "testpass",
}


def make_caldates2mqtt_settings(**overrides: Any) -> CalDates2MqttSettings:
    """Create isolated CalDates2MqttSettings for testing.

    Returns settings that ignore environment variables and .env files —
    only model defaults and explicit overrides apply.

    Note: calendars has no default and must always be provided.

    Args:
        **overrides: Field values to override defaults.

    Returns:
        CalDates2MqttSettings with deterministic values.
    """
    overrides.setdefault("calendars", [_DEFAULT_CALENDAR])
    return _IsolatedCalDates2MqttSettings(**overrides)  # type: ignore[return-value]


@pytest.fixture
def settings() -> CalDates2MqttSettings:
    """Create isolated test settings with no env variable leakage.

    Returns:
        CalDates2MqttSettings with default values, isolated from environment.
    """
    return make_caldates2mqtt_settings()
