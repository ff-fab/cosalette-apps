"""Cosalette application factory for jeelink2mqtt.

Composition root that wires domain components, adapters, and
persistence into a cosalette ``App``.  Follows the composition root
pattern (ADR-001): this module is the *only* place where concrete
implementations are assembled — all other modules depend on ports.

Shared State
~~~~~~~~~~~~

The :class:`SharedState` dataclass holds domain objects (registry,
filter bank, sensor configs) that must be accessible to both the
receiver device and the mapping command handler.  It is initialised
during the :func:`lifespan` and retrieved via :func:`get_state`.

This module-level singleton avoids polluting DI with mutable
application state while keeping the two handlers loosely coupled
(they share state through an explicit accessor, not hidden globals).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import cosalette
from cosalette.stores import JsonFileStore

from jeelink2mqtt import __version__
from jeelink2mqtt.adapters import FakeJeeLinkAdapter, PyLaCrosseAdapter
from jeelink2mqtt.filters import FilterBank
from jeelink2mqtt.models import SensorConfig
from jeelink2mqtt.ports import JeeLinkPort
from jeelink2mqtt.registry import SensorRegistry
from jeelink2mqtt.settings import Jeelink2MqttSettings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared application state
# ---------------------------------------------------------------------------


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


_state: SharedState | None = None


def get_state() -> SharedState:
    """Return the shared application state.

    Raises:
        RuntimeError: If called outside the application lifespan.
    """
    if _state is None:
        msg = "Application state not initialised — are you inside the app lifespan?"
        raise RuntimeError(msg)
    return _state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(ctx: cosalette.AppContext) -> AsyncIterator[None]:
    """Application lifespan — initialise and tear down shared state.

    **Why here?**  The registry, filter bank, and sensor config lookup
    must exist before any device or command handler runs.  The lifespan
    runs *after* adapter resolution but *before* devices start — the
    ideal hook for one-time domain initialisation.
    """
    global _state  # noqa: PLW0603
    settings: Jeelink2MqttSettings = ctx.settings  # type: ignore[assignment]

    configs = _build_sensor_configs(settings)
    _state = SharedState(
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
        yield
    finally:
        _state = None
        logger.info("Shared state torn down")


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def _make_adapter(settings: Jeelink2MqttSettings) -> PyLaCrosseAdapter:
    """Factory for the production JeeLink adapter.

    Receives ``Jeelink2MqttSettings`` via cosalette's signature-based
    DI at adapter-resolution time (see ``_call_factory`` in cosalette).
    """
    return PyLaCrosseAdapter(port=settings.serial_port, baud_rate=settings.baud_rate)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> cosalette.App:
    """Create and wire the jeelink2mqtt cosalette application.

    This is the **composition root** — the single place where all
    domain components, adapters, and infrastructure are assembled.

    Returns:
        A fully-configured :class:`cosalette.App` ready to ``run()``
        or ``cli()``.
    """
    app = cosalette.App(
        name="jeelink2mqtt",
        version=__version__,
        description="JeeLink LaCrosse sensor bridge for MQTT",
        settings_class=Jeelink2MqttSettings,
        lifespan=_lifespan,
        store=JsonFileStore(Path("data") / "jeelink2mqtt.json"),
        adapters={JeeLinkPort: (_make_adapter, FakeJeeLinkAdapter)},
    )

    # Deferred imports avoid circular deps — both modules import
    # from *this* file (get_state / SharedState).
    from jeelink2mqtt.commands import register_commands
    from jeelink2mqtt.receiver import register_receiver

    register_receiver(app)
    register_commands(app)

    return app
