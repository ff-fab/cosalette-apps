"""Application configuration for jeelink2mqtt.

Extends cosalette's ``Settings`` base with JeeLink-specific fields
for serial communication, sensor definitions, and signal-processing
parameters.  Loaded from environment variables prefixed with
``JEELINK2MQTT_`` and/or a ``.env`` file.
"""

from __future__ import annotations

from typing import Annotated

import cosalette
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import SettingsConfigDict


class SensorConfigSettings(BaseModel):
    """Pydantic model for a single sensor definition in the config.

    Mirrors :class:`~jeelink2mqtt.models.SensorConfig` but lives in
    the settings layer so pydantic-settings can deserialise it from
    environment variables or config files.
    """

    name: str
    """Logical sensor name (e.g. ``"office"``, ``"outdoor"``)."""

    temp_offset: float = 0.0
    """Calibration offset for temperature (°C)."""

    humidity_offset: float = 0.0
    """Calibration offset for humidity (percentage points)."""

    staleness_timeout: float | None = None
    """Per-sensor staleness override in seconds (``None`` = use global)."""


class Jeelink2MqttSettings(cosalette.Settings):
    """Root settings for the jeelink2mqtt application.

    Inherits MQTT and logging settings from cosalette and adds
    hardware, sensor, and signal-processing configuration.

    Environment variable examples::

        JEELINK2MQTT_SERIAL_PORT=/dev/ttyUSB0
        JEELINK2MQTT_BAUD_RATE=57600
        JEELINK2MQTT_STALENESS_TIMEOUT_SECONDS=600
        JEELINK2MQTT_MQTT__HOST=broker.local
    """

    model_config = SettingsConfigDict(
        env_prefix="JEELINK2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # -- Serial / hardware --------------------------------------------------

    serial_port: str = Field(
        default="/dev/ttyUSB0",
        description="Serial port for the JeeLink USB receiver.",
    )

    baud_rate: int = Field(
        default=57600,
        description="Serial baud rate.",
    )

    # -- Sensor definitions --------------------------------------------------

    sensors: list[SensorConfigSettings] = Field(
        default_factory=list,
        description="Configured sensor definitions.",
    )

    # -- Timing & signal processing ------------------------------------------

    staleness_timeout_seconds: Annotated[
        float,
        Field(
            default=600.0,
            ge=60.0,
            description=("Global staleness timeout in seconds (default: 10 minutes)."),
        ),
    ]

    median_filter_window: Annotated[
        int,
        Field(
            default=7,
            ge=3,
            le=21,
            description=(
                "Median filter window size (must be odd for unambiguous median)."
            ),
        ),
    ]

    heartbeat_interval_seconds: Annotated[
        float,
        Field(
            default=180.0,
            ge=10.0,
            description=("Publish interval when values haven't changed (seconds)."),
        ),
    ]

    # -- Validators ----------------------------------------------------------

    @field_validator("serial_port")
    @classmethod
    def _serial_port_must_be_device_path(cls, value: str) -> str:
        """Ensure the serial port looks like a Unix device path."""
        if not value.startswith("/dev/"):
            msg = f"serial_port must start with '/dev/', got {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("median_filter_window")
    @classmethod
    def _median_window_must_be_odd(cls, value: int) -> int:
        """An odd window size ensures an unambiguous median value."""
        if value % 2 == 0:
            msg = f"median_filter_window must be odd, got {value}"
            raise ValueError(msg)
        return value
