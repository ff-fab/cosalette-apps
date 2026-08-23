"""Application settings for wiz2mqtt.

Extends cosalette's Settings with the WIZ2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or CLI flags.
Priority: CLI > env > .env > defaults.

Bulb inventory and colour-model settings land in cap-10u.9.
"""

import cosalette
from pydantic_settings import SettingsConfigDict


class Wiz2MqttSettings(cosalette.Settings):
    """wiz2mqtt application settings."""

    model_config = SettingsConfigDict(
        env_prefix="WIZ2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )
