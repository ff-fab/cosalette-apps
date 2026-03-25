"""Configuration test fixtures.

Provides fixtures for testing Airthings2MqttSettings.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_settings import PydanticBaseSettingsSource

from airthings2mqtt.settings import Airthings2MqttSettings


class _IsolatedAirthings2MqttSettings(Airthings2MqttSettings):
    """Airthings2MqttSettings subclass that ignores ambient configuration.

    Overrides settings_customise_sources to use only init_settings,
    stripping env vars, .env files, and secrets. This ensures tests
    are fully deterministic regardless of the host environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[Airthings2MqttSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def make_airthings2mqtt_settings(**overrides: Any) -> Airthings2MqttSettings:
    """Create isolated Airthings2MqttSettings for testing.

    Returns settings that ignore environment variables and .env files —
    only model defaults and explicit overrides apply.

    Note: device_mac has no default and must always be provided.

    Args:
        **overrides: Field values to override defaults.

    Returns:
        Airthings2MqttSettings with deterministic values.
    """
    overrides.setdefault("device_mac", "AA:BB:CC:DD:EE:FF")
    return _IsolatedAirthings2MqttSettings(**overrides)  # type: ignore[return-value]


@pytest.fixture
def settings() -> Airthings2MqttSettings:
    """Create isolated test settings with no env variable leakage.

    Returns:
        Airthings2MqttSettings with default values, isolated from environment.
    """
    return make_airthings2mqtt_settings()
