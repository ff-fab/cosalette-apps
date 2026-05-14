"""Shared application state for jeelink2mqtt.

Contains the :class:`SharedState` dataclass and the helper to build
domain sensor configs from settings.  Both the receiver device and the
mapping command handler depend on ``SharedState`` — keeping it in a
leaf module avoids circular imports with the composition root.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, cast

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings

logger = logging.getLogger(__name__)


class RegistryStore(Protocol):
    """Minimal persistence surface used by SharedState."""

    def get(self, key: str, default: object = None) -> object: ...

    def __setitem__(self, key: str, value: object) -> None: ...


@dataclass
class SharedState:
    """Shared mutable state initialised during app state factory.

    Holds the domain objects that both the receiver device and
    mapping command handler need to access.
    """

    registry: SensorRegistry
    """Sensor ID → name registry (auto-adopt + manual assign)."""

    filter_bank: FilterBank
    """Per-sensor median filters for outlier rejection."""

    sensor_configs: dict[str, SensorConfig] = field(default_factory=dict)
    """Lookup table of domain sensor configs keyed by name."""

    last_readings: dict[str, SensorReading] = field(default_factory=dict)
    """Last calibrated reading per sensor (for heartbeat re-publish)."""

    last_publish_time: dict[str, datetime] = field(default_factory=dict)
    """Last publish timestamp per sensor (for heartbeat interval tracking)."""

    last_availability: dict[str, str] = field(default_factory=dict)
    """Last published availability per sensor (``'online'`` or ``'offline'``).

    Used by staleness_checker to avoid duplicate retained offline publishes
    and to correct availability when a sensor recovers mid-publish.
    """

    def restore_from(
        self, store: RegistryStore, settings: Jeelink2MqttSettings
    ) -> None:
        """Restore persisted registry state from the device store.

        If the store contains a "registry" key from a previous run,
        we rebuild the SensorRegistry from that snapshot so
        ID→name mappings survive restarts.
        """
        registry_data = store.get("registry")
        if registry_data is None:
            logger.info("No persisted registry state — starting fresh")
            return

        if not isinstance(registry_data, dict):
            logger.warning("Invalid persisted registry data — starting fresh")
            return

        configs = list(self.sensor_configs.values())
        try:
            self.registry = SensorRegistry.from_dict(
                cast(dict[str, Any], registry_data),
                sensors=configs,
                staleness_timeout=settings.staleness_timeout_seconds,
            )
        except KeyError, TypeError, ValueError:
            logger.warning("Corrupt persisted registry data — starting fresh")
            return
        logger.info(
            "Restored registry with %d mapping(s)",
            len(self.registry.get_all_mappings()),
        )

    def record_published_reading(
        self, name: str, reading: SensorReading, published_at: datetime
    ) -> None:
        """Record a published reading for heartbeat re-publishing."""
        self.last_readings[name] = reading
        self.last_publish_time[name] = published_at
        self.last_availability[name] = "online"

    def persist_registry_if_due(
        self,
        store: RegistryStore,
        now: datetime,
        last_persist_time: datetime,
        interval_seconds: float = 60.0,
    ) -> datetime | None:
        """Persist registry if interval has elapsed.

        Periodic background writer — fires when *interval_seconds* have elapsed
        since the last persist.  See also
        :func:`jeelink2mqtt.main._persist_registry` for the event-driven writer
        called by the ``on_registry_events`` reactor and mapping command handlers.

        Returns the new persist time if persisted, None otherwise.
        """
        if (now - last_persist_time).total_seconds() >= interval_seconds:
            store["registry"] = self.registry.to_dict()
            return now
        return None


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


def build_shared_state(settings: Jeelink2MqttSettings) -> SharedState:
    """Build SharedState with registry, filter bank, and sensor configs.

    Factory function for @app.state decorator.
    """
    configs = _build_sensor_configs(settings)
    return SharedState(
        registry=SensorRegistry(configs, settings.staleness_timeout_seconds),
        filter_bank=FilterBank(settings.median_filter_window),
        sensor_configs={c.name: c for c in configs},
    )
