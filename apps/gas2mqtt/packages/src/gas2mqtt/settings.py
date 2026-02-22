"""Application settings for gas2mqtt.

Extends cosalette's Settings with gas meter-specific configuration.
All settings are loaded from environment variables (GAS2MQTT_ prefix),
.env files, or CLI flags. Priority: CLI > env > .env > defaults.
"""

from pathlib import Path

import cosalette
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Gas2MqttSettings(cosalette.Settings):
    """Gas meter monitoring settings.

    Extends cosalette base settings with sensor, trigger, temperature,
    and consumption tracking configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="GAS2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # I2C configuration
    i2c_bus: int = Field(
        default=1,
        ge=0,
        description="I2C bus number (1 for newer Raspberry Pi)",
    )
    i2c_address: int = Field(
        default=0x0D,
        description="I2C address of QMC5883L magnetometer",
    )

    # Schmitt trigger configuration
    trigger_level: int = Field(
        default=-5000,
        description="Bz trigger threshold",
    )
    trigger_hysteresis: int = Field(
        default=700,
        ge=0,
        description="Schmitt trigger hysteresis band",
    )

    # Polling configuration
    poll_interval: float = Field(
        default=1.0,
        gt=0,
        description="Gas counter polling interval in seconds",
    )
    temperature_interval: float = Field(
        default=300.0,
        gt=0,
        description="Temperature reporting interval in seconds",
    )

    # Temperature calibration (empirical: temp_celsius = temp_scale * raw + temp_offset)
    temp_scale: float = Field(
        default=0.008,
        description="Temperature calibration scale factor",
    )
    temp_offset: float = Field(
        default=20.3,
        description="Temperature calibration offset",
    )
    ewma_alpha: float = Field(
        default=0.2,
        gt=0,
        le=1,
        description="EWMA smoothing factor (0-1)",
    )

    # Consumption tracking
    enable_consumption_tracking: bool = Field(
        default=False,
        description="Enable gas consumption tracking in m³",
    )
    liters_per_tick: float = Field(
        default=10.0,
        gt=0,
        description="Liters of gas per counter tick",
    )

    # State persistence
    state_file: Path | None = Field(
        default=None,
        description="Path to JSON file for persisting device state between "
        "restarts. When None, state is not persisted (counter and "
        "consumption reset to zero on restart).",
    )

    # Debug device
    enable_debug_device: bool = Field(
        default=False,
        description="Enable debug magnetometer telemetry device",
    )
