"""Application settings for geiger2mqtt.

Extends cosalette's Settings with the GEIGER2MQTT_ environment prefix. All
settings are loaded from environment variables, .env files, or CLI flags.
Priority: CLI > env > .env > defaults.
"""

import cosalette
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Geiger2MqttSettings(cosalette.Settings):
    """GPIO pin, conversion and timing settings for the geiger counter."""

    model_config = SettingsConfigDict(
        env_prefix="GEIGER2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    gpio_pin: int = Field(
        default=4,
        ge=0,
        description="BCM number of the GPIO pin wired to the board output",
    )
    gpio_chip: str = Field(
        default="/dev/gpiochip0",
        pattern=r"^/dev/",
        description="GPIO character device; the health check tests that it exists",
    )
    gpio_pull_up: bool = Field(
        default=False,
        description=(
            "Enable the Pi's internal pull-up resistor. Leave off when the board "
            "drives the line itself"
        ),
    )
    conversion_factor: float = Field(
        default=0.0057,
        gt=0,
        description="Dose rate in µSv/h per CPM (0.0057 for an SBM-20 tube)",
    )
    average_window: float = Field(
        default=900.0,
        ge=60,
        description="Window in seconds for the average dose rate",
    )
    publish_interval: float = Field(
        default=30.0,
        gt=0,
        description="Seconds between published readings",
    )
    no_pulse_timeout: float = Field(
        default=300.0,
        ge=0,
        description=(
            "Seconds without a pulse before the sensor is reported unavailable; "
            "0 disables the check"
        ),
    )
