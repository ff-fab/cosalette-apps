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

from cosalette import App, OnChange

from vito2mqtt.config import Vito2MqttSettings
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


def _get_interval(settings: Vito2MqttSettings, group: str) -> float:
    """Look up the polling interval for *group* from application settings.

    Args:
        settings: The application settings instance.
        group: Signal group name (must be a key in ``_INTERVAL_ATTR``).

    Returns:
        Polling interval in seconds.
    """
    return float(getattr(settings, _INTERVAL_ATTR[group]))


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
    :data:`~vito2mqtt.devices.SIGNAL_GROUPS`, using the polling
    intervals from application settings and an :class:`OnChange`
    publish strategy.

    Args:
        app: The cosalette application instance.  Must have been
            constructed with ``settings_class=Vito2MqttSettings``.
    """
    settings = app.settings
    if not isinstance(settings, Vito2MqttSettings):
        msg = (
            f"Expected Vito2MqttSettings, got {type(settings).__name__}. "
            "Ensure App was constructed with settings_class=Vito2MqttSettings."
        )
        raise TypeError(msg)

    for group_name in SIGNAL_GROUPS:
        app.add_telemetry(
            name=group_name,
            func=_make_handler(group_name),
            interval=_get_interval(settings, group_name),
            publish=OnChange(),
            group="optolink",
        )
