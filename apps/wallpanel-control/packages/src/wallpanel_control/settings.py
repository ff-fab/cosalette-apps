"""Application settings for wallpanel-control.

Extends cosalette's Settings with wallpanel-specific configuration
for SSH connectivity, backlight hardware paths, and Wake-on-LAN.
All settings are loaded from environment variables
(WALLPANEL_CONTROL_ prefix), .env files, or CLI flags.
Priority: CLI > env > .env > defaults.
"""

from __future__ import annotations

import os
import re

import cosalette
from pydantic import Field, field_validator
from pydantic_settings import SettingsConfigDict

from wallpanel_control.adapters.wol_adapter import _parse_mac

_DEVICE_RE = re.compile(r"[a-zA-Z0-9._-]+")


class WallpanelControlSettings(cosalette.Settings):
    """Wallpanel control settings.

    Extends cosalette base settings with SSH connection, hardware
    paths, and Wake-on-LAN configuration.
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
    ssh_known_hosts: str = Field(
        default="~/.ssh/known_hosts",
        description="Path to SSH known_hosts file for host-key verification",
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

    # Wake-on-LAN
    wol_mac: str = Field(
        description="MAC address for Wake-on-LAN (required)",
    )
    wol_broadcast: str = Field(
        default="255.255.255.255",
        description="Broadcast address for Wake-on-LAN packets",
    )

    @field_validator("backlight_path")
    @classmethod
    def validate_backlight_path(cls, value: str) -> str:
        """Validate the privileged backlight write path is constrained to sysfs.

        Normalises the path (collapses ``..`` without filesystem access) then
        enforces the exact shape ``/sys/class/backlight/<device>/brightness``
        where ``<device>`` contains only safe alphanumeric characters.
        """
        normalized = os.path.normpath(value)
        if not normalized.startswith(
            "/sys/class/backlight/"
        ) or not normalized.endswith("/brightness"):
            msg = "backlight_path must be an absolute /sys/class/backlight/<device>/brightness path"
            raise ValueError(msg)
        device = normalized.removeprefix("/sys/class/backlight/").removesuffix(
            "/brightness"
        )
        if not device or not _DEVICE_RE.fullmatch(device):
            msg = "backlight_path device name must contain only alphanumeric, _, -, . characters"
            raise ValueError(msg)
        return normalized

    @field_validator("wol_mac")
    @classmethod
    def validate_wol_mac(cls, value: str) -> str:
        """Validate Wake-on-LAN MAC address format at startup."""
        _parse_mac(value)
        return value
