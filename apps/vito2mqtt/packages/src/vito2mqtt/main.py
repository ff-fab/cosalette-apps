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

from cosalette import App, JsonFileStore

from vito2mqtt._store_path import resolve_store_path
from vito2mqtt._version import __version__
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices.commands import register_commands
from vito2mqtt.devices.legionella import register_legionella
from vito2mqtt.devices.telemetry import register_telemetry
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

register_telemetry(app)
register_commands(app)
register_legionella(app)

cli = app.cli
