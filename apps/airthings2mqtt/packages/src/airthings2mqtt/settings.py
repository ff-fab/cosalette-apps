"""Application settings for airthings2mqtt.

Extends cosalette's Settings with Airthings Wave BLE sensor configuration.
All settings are loaded from environment variables (AIRTHINGS2MQTT_ prefix),
.env files, or CLI flags. Priority: CLI > env > .env > defaults.
"""

from __future__ import annotations

import cosalette
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Airthings2MqttSettings(cosalette.Settings):
    """Airthings Wave BLE sensor monitoring settings.

    Extends cosalette base settings with BLE device identification
    and polling configuration for Airthings Wave sensors.
    """

    model_config = SettingsConfigDict(
        env_prefix="AIRTHINGS2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    device_name: str = Field(
        default="airthings",
        description="Friendly name for the Airthings device in MQTT topics",
    )
    device_mac: str = Field(
        description="Bluetooth MAC address of the Airthings Wave sensor",
    )
    poll_interval: int = Field(
        default=1500,
        ge=60,
        description="Polling interval in seconds (minimum 60)",
    )
