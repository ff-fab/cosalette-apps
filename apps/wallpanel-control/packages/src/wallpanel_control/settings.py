"""Application settings for wallpanel-control.

Extends cosalette's Settings with wallpanel-specific configuration
for SSH connectivity, backlight hardware paths, polling intervals,
and Wake-on-LAN. All settings are loaded from environment variables
(WALLPANEL_CONTROL_ prefix), .env files, or CLI flags.
Priority: CLI > env > .env > defaults.
"""

from __future__ import annotations

import cosalette
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class WallpanelControlSettings(cosalette.Settings):
    """Wallpanel control settings.

    Extends cosalette base settings with SSH connection, hardware
    paths, polling, and Wake-on-LAN configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="WALLPANEL_CONTROL_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # SSH configuration
    ssh_host: str = Field(
        default="wallpanel.lan",
        description="Hostname or IP address of the wallpanel",
    )
    ssh_user: str = Field(
        default="jl4",
        description="SSH username for wallpanel connection",
    )
    ssh_key_path: str = Field(
        default="~/.ssh/wallpanel",
        description="Path to SSH private key file",
    )
    ssh_port: int = Field(
        default=22,
        ge=1,
        le=65535,
        description="SSH port number",
    )
    ssh_timeout: float = Field(
        default=5.0,
        gt=0,
        description="SSH connection timeout in seconds",
    )

    # Hardware paths
    backlight_path: str = Field(
        default="/sys/class/backlight/intel_backlight/brightness",
        description="Sysfs path to backlight brightness file",
    )

    # Polling configuration
    poll_interval: float = Field(
        default=180.0,
        gt=0,
        description="Telemetry polling interval in seconds",
    )

    # Wake-on-LAN
    wol_mac: str = Field(
        description="MAC address for Wake-on-LAN (required)",
    )
    wol_broadcast: str = Field(
        default="255.255.255.255",
        description="Broadcast address for Wake-on-LAN packets",
    )
