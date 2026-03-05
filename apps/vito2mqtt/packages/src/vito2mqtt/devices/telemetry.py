# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Telemetry handler registration for all signal groups.

Registers one polling handler per signal group with the cosalette
application.  All handlers share the ``"optolink"`` coalescing group
so they execute together at coinciding tick boundaries, minimizing
serial bus sessions.  Each handler reads its group's signals from
the Optolink port and returns serialized values for MQTT publishing.

Architecture
------------
``register_telemetry(app)`` iterates over :data:`SIGNAL_GROUPS` and calls
``app.add_telemetry()`` for each group with ``group="optolink"`` to enable
tick-aligned coalescing (see ADR-007).  Handler closures are created via
the factory function ``_make_handler(group)`` to avoid the classic
late-binding closure pitfall.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from cosalette import App, OnChange, Settings

from vito2mqtt.devices import SIGNAL_GROUPS
from vito2mqtt.devices._serialization import serialize_value
from vito2mqtt.optolink.commands import COMMANDS
from vito2mqtt.ports import OptolinkPort

__all__ = ["register_telemetry"]


# ---------------------------------------------------------------------------
# Group → settings attribute mapping
# ---------------------------------------------------------------------------

_INTERVAL_ATTR: dict[str, str] = {
    "outdoor": "polling_outdoor",
    "hot_water": "polling_hot_water",
    "burner": "polling_burner",
    "heating_radiator": "polling_heating_radiator",
    "heating_floor": "polling_heating_floor",
    "system": "polling_system",
    "diagnosis": "polling_diagnosis",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make_interval(group: str) -> Callable[[Settings], float]:
    """Create a callable that extracts the polling interval from settings.

    Uses the factory pattern (like ``_make_handler``) to capture
    *group* at creation time, avoiding late-binding closure issues.

    The callable is resolved by cosalette's ``_resolve_intervals()``
    in ``_run_async()`` after settings are properly built — this
    allows registration at module-import time without requiring
    settings to be available.

    Args:
        group: Signal group name (key in ``_INTERVAL_ATTR``).

    Returns:
        Callable suitable for ``app.add_telemetry(interval=...)``.
    """
    attr = _INTERVAL_ATTR[group]

    def resolver(settings: Settings) -> float:
        return float(getattr(settings, attr))

    return resolver


def _make_handler(
    group: str,
) -> Callable[..., Awaitable[dict[str, object]]]:
    """Create an async handler closure for a signal group.

    The factory pattern avoids the late-binding closure pitfall — each
    handler captures its own *group* value at creation time rather than
    sharing a mutable loop variable.

    Args:
        group: Signal group name (key in :data:`SIGNAL_GROUPS`).

    Returns:
        Async callable suitable for ``app.add_telemetry(func=...)``.
    """

    async def handler(port: OptolinkPort) -> dict[str, object]:
        raw = await port.read_signals(SIGNAL_GROUPS[group])
        return {
            name: serialize_value(value, COMMANDS[name].type_code)
            for name, value in raw.items()
        }

    return handler


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register_telemetry(app: App) -> None:
    """Register telemetry handlers for all signal groups.

    Creates one telemetry device per group defined in
    :data:`~vito2mqtt.devices.SIGNAL_GROUPS`, using deferred polling
    intervals resolved from settings at runtime and an :class:`OnChange`
    publish strategy.

    Intervals are provided as callables (see :func:`_make_interval`)
    so that registration can happen at module-import time without
    requiring settings to be available — this allows ``--help`` and
    ``--version`` to work without environment variables.

    Args:
        app: The cosalette application instance.
    """
    for group_name in SIGNAL_GROUPS:
        app.add_telemetry(
            name=group_name,
            func=_make_handler(group_name),
            interval=_make_interval(group_name),
            publish=OnChange(),
            group="optolink",
        )
