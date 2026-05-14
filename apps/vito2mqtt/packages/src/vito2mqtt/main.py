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

"""Application composition root.

Assembles the cosalette :class:`~cosalette.App` instance, wires
adapters, registers telemetry and command handlers, and exposes
the CLI entry point.
"""

from __future__ import annotations

from cosalette import App, JsonFileStore, OnChange, setting_ref

from vito2mqtt._store_path import resolve_store_path
from vito2mqtt import __version__
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices import COMMAND_GROUPS, SIGNAL_GROUPS
from vito2mqtt.devices.commands import COMMAND_SUMMARIES, make_command_handler
from vito2mqtt.devices.legionella import legionella_device
from vito2mqtt.devices.telemetry import (
    GROUP_SUMMARIES,
    INTERVAL_ATTR,
    make_telemetry_handler,
)
from vito2mqtt.ports import OptolinkPort

__all__ = ["app", "cli"]


app = App(
    name="vito2mqtt",
    version=__version__,
    description="Viessmann boiler to MQTT bridge",
    settings_class=Vito2MqttSettings,
    store=JsonFileStore(resolve_store_path()),
    adapters={
        OptolinkPort: (
            "vito2mqtt.adapters.serial:OptolinkAdapter",
            "vito2mqtt.adapters.fake:FakeOptolinkAdapter",
        ),
    },
)

for _group in SIGNAL_GROUPS:
    app.add_telemetry(
        name=_group,
        func=make_telemetry_handler(_group),
        interval=setting_ref(INTERVAL_ATTR[_group]),
        publish=OnChange(),
        group="optolink",
        summary=GROUP_SUMMARIES[_group],
    )

for _group in COMMAND_GROUPS:
    app.add_command(
        name=_group,
        func=make_command_handler(_group),
        summary=COMMAND_SUMMARIES.get(
            _group, f"Control {_group} parameters via Optolink serial"
        ),
        payload_model=dict,
    )

app.add_device("legionella", legionella_device)

cli = app.cli
