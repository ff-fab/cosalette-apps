"""Application backward-compatibility re-exports for jeelink2mqtt.

The active composition root is :mod:`jeelink2mqtt.main`.  This module
retains the :func:`_lifespan` async context manager (for test compatibility)
and re-exports :class:`SharedState`, :func:`_build_sensor_configs`, and
:func:`build_shared_state` from :mod:`jeelink2mqtt.state` so existing
imports continue to work.

As of cosalette 0.3.13, the app uses the @app.state decorator instead
of lifespan for shared state management.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import cosalette

from jeelink2mqtt.settings import Jeelink2MqttSettings
from jeelink2mqtt.state import (  # noqa: F401
    SharedState,
    _build_sensor_configs,
    build_shared_state,
)

__all__ = ["SharedState", "_build_sensor_configs", "build_shared_state", "_lifespan"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(ctx: cosalette.AppContext) -> AsyncIterator[SharedState]:
    """Application lifespan — initialise and tear down shared state.

    DEPRECATED: This function is retained for backward compatibility with tests.
    The active app now uses the @app.state decorator instead of lifespan.

    Runs *after* adapter resolution but *before* devices start,
    building the :class:`SharedState` (registry, filter bank, sensor
    config lookup) that both the receiver and command handler inject.
    """
    warnings.warn(
        "_lifespan() is deprecated; the app now uses @app.state in main.py.",
        DeprecationWarning,
        stacklevel=2,
    )
    settings: Jeelink2MqttSettings = ctx.settings  # type: ignore

    state = build_shared_state(settings)

    logger.info(
        "Shared state ready — %d sensor(s): %s",
        len(state.sensor_configs),
        ", ".join(state.sensor_configs.keys()) or "(none)",
    )

    try:
        yield state
    finally:
        logger.info("Shared state torn down")
