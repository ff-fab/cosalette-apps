"""Application settings for airthings2mqtt.

Extends cosalette's Settings with Airthings Wave BLE sensor configuration.
All settings are loaded from environment variables (AIRTHINGS2MQTT_ prefix),
.env files, or CLI flags. Priority: CLI > env > .env > defaults.
"""

from __future__ import annotations

import cosalette
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class _MqttSettings(cosalette.MqttSettings):
    """MQTT settings pinned to the pre-0.7.0 ``tls=False`` default.

    cosalette 0.7.0 flipped ``MqttSettings.tls`` to ``True`` (ADR-062,
    F-CU1). Redeclaring the field here preserves this app's existing
    runtime behaviour, so upgrading never silently starts a TLS handshake
    the broker cannot answer. Deployments opt in per environment with
    ``AIRTHINGS2MQTT_MQTT__TLS=true``.

    A ``default_factory`` only works here because ``mqtt`` is annotated as this
    subclass with ``tls=False`` overridden. If the field stayed typed as the
    base ``MqttSettings``, sibling ``MQTT__*`` variables would restore
    ``tls=True`` during nested-model reconstruction.
    """

    tls: bool = False


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

    mqtt: _MqttSettings = Field(default_factory=_MqttSettings)

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
    poll_timeout: float = Field(
        default=120.0,
        ge=5.0,
        description=(
            "Per-invocation timeout in seconds bounding each BLE poll (minimum 5). "
            "Backs the cosalette telemetry timeout so a wedged read raises "
            "TimeoutError instead of hanging indefinitely. The 5s floor guards "
            "against misconfiguration (e.g. a '1.2' typo for '120') that would "
            "otherwise clip every read."
        ),
    )
