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

"""App wiring helper — single source of truth for handler registration.

Called from both the production composition root (:mod:`vito2mqtt.main`)
and the integration-test fixture builder.  Keeping registration in one
place prevents production/test drift when signal groups or devices change.
"""

from __future__ import annotations

from cosalette import App, OnChange, setting_ref

from vito2mqtt.devices import COMMAND_GROUPS, SIGNAL_GROUPS
from vito2mqtt.devices.commands import COMMAND_SUMMARIES, make_command_handler
from vito2mqtt.devices.legionella import legionella_device
from vito2mqtt.devices.telemetry import (
    GROUP_SUMMARIES,
    INTERVAL_ATTR,
    make_telemetry_handler,
)

__all__ = ["configure_app"]


def configure_app(app: App) -> None:
    """Wire telemetry, commands, and the legionella device onto *app*.

    Registers one telemetry handler per :data:`~vito2mqtt.devices.SIGNAL_GROUPS`
    entry, one command handler per :data:`~vito2mqtt.devices.COMMAND_GROUPS`
    entry, and the legionella device.

    Args:
        app: Cosalette :class:`~cosalette.App` instance to configure.
    """
    for group in SIGNAL_GROUPS:
        app.add_telemetry(
            name=group,
            func=make_telemetry_handler(group),
            interval=setting_ref(INTERVAL_ATTR[group]),
            publish=OnChange(),
            group="optolink",
            summary=GROUP_SUMMARIES[group],
        )
    for group in COMMAND_GROUPS:
        app.add_command(
            name=group,
            func=make_command_handler(group),
            summary=COMMAND_SUMMARIES.get(
                group, f"Control {group} parameters via Optolink serial"
            ),
            payload_model=dict,
        )
    app.add_device("legionella", legionella_device)
