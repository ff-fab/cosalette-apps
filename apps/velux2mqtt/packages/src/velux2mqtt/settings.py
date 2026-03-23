"""Application settings for velux2mqtt.

Extends cosalette's Settings with Velux cover configuration.
All settings are loaded from environment variables (VELUX2MQTT_ prefix),
.env files, or CLI flags. Priority: CLI > env > .env > defaults.

Covers are configured as a JSON list via VELUX2MQTT_COVERS.
"""

from __future__ import annotations

from typing import Literal

import cosalette
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import SettingsConfigDict


class CoverConfig(BaseModel):
    """Configuration for a single Velux cover (blind or window).

    Each cover maps to one KLF 050 remote controlled via three GPIO pins
    through an M74HC4066 analog switch IC.
    """

    name: str = Field(description="Unique cover identifier (e.g. 'blind', 'window')")
    pin_up: int = Field(ge=0, le=27, description="BCM GPIO pin for UP/OPEN button")
    pin_stop: int = Field(ge=0, le=27, description="BCM GPIO pin for STOP button")
    pin_down: int = Field(ge=0, le=27, description="BCM GPIO pin for DOWN/CLOSE button")
    travel_duration_up: float = Field(
        gt=0,
        description="Seconds for full upward (open) travel",
    )
    travel_duration_down: float = Field(
        gt=0,
        description="Seconds for full downward (close) travel",
    )
    travel_time_offset: float = Field(
        default=1.0,
        ge=0,
        description="Seconds subtracted from elapsed time to account for "
        "motor start/stop lag",
    )
    max_timer_margin: float = Field(
        default=2.0,
        ge=0,
        description="Extra seconds added to travel duration for the safety "
        "cutoff timer",
    )
    measure_offset: bool = Field(
        default=False,
        description="Whether to measure travel_time_offset during calibration. "
        "When False, calibration skips the TIMING_OFFSET state and uses the "
        "manually-configured travel_time_offset value.",
    )
    dead_band_pct: float = Field(
        default=0.0,
        ge=0,
        lt=100,
        description="Percentage of total travel consumed by handle rotation "
        "before actual cover movement begins (0 disables dead band)",
    )

    @model_validator(mode="after")
    def _pins_unique(self) -> CoverConfig:
        pins = [self.pin_up, self.pin_stop, self.pin_down]
        if len(set(pins)) != len(pins):
            msg = (
                f"Cover '{self.name}': pin_up, pin_stop, and pin_down "
                f"must be distinct (got {pins})"
            )
            raise ValueError(msg)
        return self


class Velux2MqttSettings(cosalette.Settings):
    """Velux cover control settings.

    Extends cosalette base settings with cover definitions, GPIO timing,
    homing, calibration, and drift compensation configuration.
    """

    model_config = SettingsConfigDict(
        env_prefix="VELUX2MQTT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Cover definitions (JSON list)
    covers: list[CoverConfig] = Field(
        default_factory=list,
        description="List of cover configurations. Each cover maps to one "
        "KLF 050 remote with three GPIO pins.",
    )

    # Global GPIO timing
    button_press_duration: float = Field(
        default=0.5,
        gt=0,
        description="Seconds to hold GPIO HIGH to simulate a button press",
    )

    # Startup homing
    enable_startup_homing: bool = Field(
        default=True,
        description="On startup, move all covers to a known endpoint to "
        "establish a reference position",
    )
    homing_direction: Literal["open", "close"] = Field(
        default="close",
        description="Direction to move during startup homing "
        "('open' = 100%, 'close' = 0%)",
    )

    # Calibration
    calibration_runs: int = Field(
        default=3,
        ge=1,
        description="Number of measurement runs per direction during calibration",
    )

    # Drift compensation
    drift_recalibration_threshold: int = Field(
        default=2,
        ge=0,
        description="After this many consecutive intermediate moves, "
        "recalibrate via an endpoint. 0 disables drift compensation.",
    )

    @model_validator(mode="after")
    def _covers_unique_names(self) -> Velux2MqttSettings:
        names = [c.name for c in self.covers]
        if len(set(names)) != len(names):
            dupes = [n for n in names if names.count(n) > 1]
            msg = f"Cover names must be unique, duplicates: {set(dupes)}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _covers_no_pin_overlap(self) -> Velux2MqttSettings:
        all_pins: dict[int, str] = {}
        for cover in self.covers:
            for pin_name, pin in [
                ("pin_up", cover.pin_up),
                ("pin_stop", cover.pin_stop),
                ("pin_down", cover.pin_down),
            ]:
                if pin in all_pins:
                    msg = (
                        f"GPIO pin {pin} used by both '{all_pins[pin]}' "
                        f"and '{cover.name}.{pin_name}'"
                    )
                    raise ValueError(msg)
                all_pins[pin] = f"{cover.name}.{pin_name}"
        return self
