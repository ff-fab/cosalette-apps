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
    trigger_min_interval: float = Field(
        default=30.0,
        gt=0,
        description=(
            "Minimum spacing in seconds between trigger-initiated reads "
            "(cosalette ADR-066). airthings2mqtt/airthings/set is a public MQTT "
            "topic; a held dashboard button or an automation loop would otherwise "
            "queue one BLE round-trip per message, draining a battery-powered "
            "sensor. A wake inside a closed window is held, not dropped. Raise it "
            "for a flakier sensor or to conserve battery; lower it for snappier "
            "on-demand reads at the cost of more frequent BLE connects. Keep it "
            "well under poll_interval so it never throttles the scheduled cadence."
        ),
    )
