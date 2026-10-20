"""Application settings for geiger2mqtt.

Extends cosalette's Settings with the GEIGER2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or CLI flags.
Priority: CLI > env > .env > defaults.
"""

import cosalette
from pydantic_settings import SettingsConfigDict


class Geiger2MqttSettings(cosalette.Settings):
    """geiger2mqtt application settings."""

    model_config = SettingsConfigDict(
        env_prefix="GEIGER2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )
