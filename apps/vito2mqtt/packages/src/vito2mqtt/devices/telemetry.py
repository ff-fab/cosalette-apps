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

"""Telemetry handler factory and metadata for all signal groups.

Exports handler factories and spec dicts consumed by the composition
root.  All handlers share the ``"optolink"`` coalescing group so they
execute together at coinciding tick boundaries, minimizing serial bus
sessions.  Each handler reads its group's signals from the Optolink
port and returns serialized values for MQTT publishing.

Architecture
------------
:func:`make_telemetry_handler` creates a closure per group to avoid the
classic late-binding pitfall.  :data:`INTERVAL_ATTR` maps each group to
its settings attribute name for deferred polling interval resolution.
:data:`GROUP_SUMMARIES` provides human-readable OpenAPI summaries.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from vito2mqtt.devices import SIGNAL_GROUPS
from vito2mqtt.devices._serialization import serialize_value
from vito2mqtt.optolink.commands import COMMANDS
from vito2mqtt.ports import OptolinkPort

__all__ = ["make_telemetry_handler", "INTERVAL_ATTR", "GROUP_SUMMARIES"]


# ---------------------------------------------------------------------------
# Group → settings attribute mapping
# ---------------------------------------------------------------------------

INTERVAL_ATTR: dict[str, str] = {
    "outdoor": "polling_outdoor",
    "hot_water": "polling_hot_water",
    "burner": "polling_burner",
    "heating_radiator": "polling_heating_radiator",
    "heating_floor": "polling_heating_floor",
    "system": "polling_system",
    "diagnosis": "polling_diagnosis",
}

GROUP_SUMMARIES: dict[str, str] = {
    "outdoor": "Read outdoor temperature sensors via Optolink serial",
    "hot_water": "Read hot water temperature sensors via Optolink serial",
    "burner": "Read burner temperature, modulation and runtime data via Optolink serial",
    "heating_radiator": "Read radiator heating circuit temperatures and pump status via Optolink serial",
    "heating_floor": "Read floor heating circuit temperatures and pump status via Optolink serial",
    "system": "Read Vitotronic system status and operational parameters via Optolink serial",
    "diagnosis": "Read diagnostic error codes and system health data via Optolink serial",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def make_telemetry_handler(
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
