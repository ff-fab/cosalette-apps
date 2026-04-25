"""Application lifespan and backward-compatibility re-exports for jeelink2mqtt.

The active composition root is :mod:`jeelink2mqtt.main`.  This module
retains the :func:`_lifespan` async context manager (imported by tests)
and re-exports :class:`SharedState` and :func:`_build_sensor_configs`
from :mod:`jeelink2mqtt.state` so existing imports continue to work.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import cosalette

from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import SharedState, _build_sensor_configs  # noqa: F401

__all__ = ["SharedState", "_build_sensor_configs", "_lifespan"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(ctx: cosalette.AppContext) -> AsyncIterator[SharedState]:
    """Application lifespan — initialise and tear down shared state.

    Runs *after* adapter resolution but *before* devices start,
    building the :class:`SharedState` (registry, filter bank, sensor
    config lookup) that both the receiver and command handler inject.
    """
    settings: Jeelink2MqttSettings = ctx.settings  # type: ignore

    configs = _build_sensor_configs(settings)
    state = SharedState(
        registry=SensorRegistry(configs, settings.staleness_timeout_seconds),
        filter_bank=FilterBank(settings.median_filter_window),
        sensor_configs={c.name: c for c in configs},
    )

    logger.info(
        "Shared state ready — %d sensor(s): %s",
        len(configs),
        ", ".join(c.name for c in configs) or "(none)",
    )

    try:
        yield state
    finally:
        logger.info("Shared state torn down")
