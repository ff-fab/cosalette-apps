"""Isolated settings and a manual clock for geiger2mqtt tests."""

from __future__ import annotations

from typing import Any

from pydantic_settings import PydanticBaseSettingsSource

from geiger2mqtt.settings import Geiger2MqttSettings


class _IsolatedSettings(Geiger2MqttSettings):
    """Settings that ignore env vars and .env files: defaults plus overrides."""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[Geiger2MqttSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


def make_settings(**overrides: Any) -> Geiger2MqttSettings:
    """Return deterministic settings, isolated from the host environment."""
    return _IsolatedSettings(**overrides)


class FakeTime:
    """Callable monotonic clock that only moves when a test advances it."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
