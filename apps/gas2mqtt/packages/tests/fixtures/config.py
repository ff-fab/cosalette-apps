"""Configuration test fixtures.

Provides fixtures for testing Gas2MqttSettings.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_settings import PydanticBaseSettingsSource

from gas2mqtt.settings import Gas2MqttSettings


class _IsolatedGas2MqttSettings(Gas2MqttSettings):
    """Gas2MqttSettings subclass that ignores ambient configuration.

    Overrides settings_customise_sources to use only init_settings,
    stripping env vars, .env files, and secrets. This ensures tests
    are fully deterministic regardless of the host environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[Gas2MqttSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def make_gas2mqtt_settings(**overrides: Any) -> Gas2MqttSettings:
    """Create isolated Gas2MqttSettings for testing.

    Returns Gas2MqttSettings that ignores environment variables and
    .env files — only model defaults and explicit overrides apply.

    Args:
        **overrides: Field values to override defaults.

    Returns:
        Gas2MqttSettings with deterministic values.
    """
    return _IsolatedGas2MqttSettings(**overrides)  # type: ignore[return-value]


@pytest.fixture
def settings() -> Gas2MqttSettings:
    """Create isolated test settings with no env variable leakage.

    Returns:
        Gas2MqttSettings with default values, isolated from environment.
    """
    return make_gas2mqtt_settings()
