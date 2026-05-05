"""Shared application state for jeelink2mqtt.

Contains the :class:`SharedState` dataclass and the helper to build
domain sensor configs from settings.  Both the receiver device and the
mapping command handler depend on ``SharedState`` — keeping it in a
leaf module avoids circular imports with the composition root.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from jeelink2mqtt.calibration import apply_calibration
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig, SensorReading
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings

if TYPE_CHECKING:
    from cosalette import DeviceContext as PublishableDeviceContext
    from cosalette import DeviceStore

logger = logging.getLogger(__name__)


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

    def restore_from(self, store: DeviceStore, settings: Jeelink2MqttSettings) -> None:
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

    def apply_pipeline(
        self, reading: SensorReading, config: SensorConfig
    ) -> SensorReading:
        """Filter → calibrate a raw reading, returning a new SensorReading."""
        temp, humidity = self.filter_bank.filter(reading)
        filtered = replace(reading, temperature=temp, humidity=int(humidity))
        return apply_calibration(filtered, config)

    def record_published_reading(
        self, name: str, reading: SensorReading, published_at: datetime
    ) -> None:
        """Record a published reading for heartbeat re-publishing."""
        self.last_readings[name] = reading
        self.last_publish_time[name] = published_at

    async def flush_events(
        self,
        ctx: PublishableDeviceContext,
        store: DeviceStore,
    ) -> bool:
        """Drain registry events, publish mapping state/events, persist registry.

        Returns True if events were flushed.
        """
        events = self.registry.drain_events()
        if not events:
            return False

        # Publish mapping events and reset filter bank for reassigned sensors
        for event in events:
            await self._publish_mapping_event(ctx, event)
            if event.old_sensor_id is not None:
                self.filter_bank.reset(event.old_sensor_id)

        # Publish current mapping state and persist registry
        await self._publish_mapping_state(ctx)
        store["registry"] = self.registry.to_dict()
        return True

    def persist_registry_if_due(
        self,
        store: DeviceStore,
        now: datetime,
        last_persist_time: datetime,
        interval_seconds: float = 60.0,
    ) -> datetime | None:
        """Persist registry if interval has elapsed.

        Returns the new persist time if persisted, None otherwise.
        """
        if (now - last_persist_time).total_seconds() >= interval_seconds:
            store["registry"] = self.registry.to_dict()
            return now
        return None

    async def _publish_mapping_event(
        self,
        ctx: PublishableDeviceContext,
        event,
    ) -> None:
        """Publish a mapping change event (non-retained)."""
        payload = json.dumps(
            {
                "event_type": event.event_type,
                "sensor_name": event.sensor_name,
                "old_sensor_id": event.old_sensor_id,
                "new_sensor_id": event.new_sensor_id,
                "timestamp": event.timestamp.isoformat(),
                "reason": event.reason,
            }
        )
        await ctx.publish("mapping/event", payload, retain=False)

    async def _publish_mapping_state(self, ctx: PublishableDeviceContext) -> None:
        """Publish current mapping state snapshot (retained)."""
        mapping_state = {
            name: {
                "sensor_id": m.sensor_id,
                "mapped_at": m.mapped_at.isoformat(),
                "last_seen": m.last_seen.isoformat(),
            }
            for name, m in self.registry.get_all_mappings().items()
        }
        await ctx.publish("mapping/state", json.dumps(mapping_state), retain=True)


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
