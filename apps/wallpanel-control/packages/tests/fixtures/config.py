"""Configuration test fixtures.

Provides fixtures for testing WallpanelControlSettings.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_settings import PydanticBaseSettingsSource

from wallpanel_control.settings import WallpanelControlSettings


class _IsolatedWallpanelControlSettings(WallpanelControlSettings):
    """WallpanelControlSettings subclass that ignores ambient configuration.

    Overrides settings_customise_sources to use only init_settings,
    stripping env vars, .env files, and secrets. This ensures tests
    are fully deterministic regardless of the host environment.
    """

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[WallpanelControlSettings],  # noqa: ARG003
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        dotenv_settings: PydanticBaseSettingsSource,  # noqa: ARG003
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings,)


_REQUIRED_DEFAULTS: dict[str, Any] = {
    "wol_mac": "AA:BB:CC:DD:EE:FF",
}


def make_wallpanel_control_settings(**overrides: Any) -> WallpanelControlSettings:
    """Create isolated WallpanelControlSettings for testing.

    Returns WallpanelControlSettings that ignores environment variables
    and .env files — only model defaults and explicit overrides apply.
    Required fields without defaults (wol_mac) are provided automatically
    unless explicitly overridden.

    Args:
        **overrides: Field values to override defaults.

    Returns:
        WallpanelControlSettings with deterministic values.
    """
    merged = {**_REQUIRED_DEFAULTS, **overrides}
    return _IsolatedWallpanelControlSettings(**merged)  # type: ignore[return-value]


@pytest.fixture
def settings() -> WallpanelControlSettings:
    """Create isolated test settings with no env variable leakage.

    Returns:
        WallpanelControlSettings with default values, isolated from environment.
    """
    return make_wallpanel_control_settings()
