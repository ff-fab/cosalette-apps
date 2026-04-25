"""Shared application state for jeelink2mqtt.

Contains the :class:`SharedState` dataclass and the helper to build
domain sensor configs from settings.  Both the receiver device and the
mapping command handler depend on ``SharedState`` — keeping it in a
leaf module avoids circular imports with the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings


@dataclass
class SharedState:
    """Shared mutable state initialised during lifespan.

    Holds the domain objects that both the receiver device and
    mapping command handler need to access.
    """

    registry: SensorRegistry
    """Sensor ID → name registry (auto-adopt + manual assign)."""

    filter_bank: FilterBank
    """Per-sensor median filters for outlier rejection."""

    sensor_configs: dict[str, SensorConfig] = field(default_factory=dict)
    """Lookup table of domain sensor configs keyed by name."""


def _build_sensor_configs(settings: Jeelink2MqttSettings) -> list[SensorConfig]:
    """Convert settings-layer sensor definitions to domain SensorConfig."""
    return [
        SensorConfig(
            name=s.name,
            temp_offset=s.temp_offset,
            humidity_offset=s.humidity_offset,
            staleness_timeout=s.staleness_timeout,
        )
        for s in settings.sensors
    ]
