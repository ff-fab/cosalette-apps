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
from vito2mqtt.devices.telemetry_models import GROUP_STATE_MODELS
from vito2mqtt.errors import OptolinkConnectionError, OptolinkTimeoutError

__all__ = [
    "configure_app",
    "COMMAND_WAKE_MIN_INTERVAL_SECONDS",
    "COMMAND_TIMEOUT_SECONDS",
]

COMMAND_TIMEOUT_SECONDS = 90.0
"""Per-invocation backstop for every Optolink command handler (seconds).

cosalette 0.7.0 (ADR-060) made an omitted ``timeout=`` a bounded 30 s
default. A full command payload for a group like ``heating_radiator`` is
13 READ_WRITE signals (seven of them 8-byte weekly-timer blocks): the
handler batch-reads all 13 for the read-before-write guard, then batch-
writes the changed ones, and each batch can queue behind an in-flight
``optolink`` telemetry cycle (``diagnosis`` is 11 reads) before its own
I/O starts on the shared 4800-baud bus. Sizing conservatively at ~0.5 s
per telegram round trip, that worst case is ~34 s — over the 30 s
default, which would cancel a legitimate schedule write mid-batch. 90 s
clears it with margin while still bounding a wedged bus. Paired with
``unavailable_on`` so a timeout also marks the device offline, and with
the ``asyncio.shield`` in ``OptolinkAdapter.write_signals`` so a healthy
bus still lands every signal after the cancel unwinds (cap-ug0).
"""

COMMAND_WAKE_MIN_INTERVAL_SECONDS = 15.0
"""Floor on the spacing between two command-triggered telemetry runs (seconds).

Each signal group is registered ``triggerable="local"`` so a successful
command write can wake its telemetry member immediately (ADR-007 §
Command-Triggered Refresh, cosalette ADR-066/ADR-067).  The Optolink is a
single 4800-baud serial bus: a burst of writes — a full weekly timer
schedule arrives as seven separate ``/set`` payloads — would otherwise
queue seven full group reads behind it.  The throttle bounds
*trigger-initiated* run starts only; the ``interval=`` heartbeat is
untouched, and an arm landing inside a closed window is held, not
dropped, so the last write in a burst is still reflected.
"""


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
            # cosalette ADR-067: a group= member may declare a trigger
            # source; the wake batches that member into the group's own
            # cycle, so Optolink bus exclusion is preserved.  "local"
            # subscribes no MQTT topic — the only arming path is the
            # EntityNotifier call in the command handler.
            triggerable="local",
            min_interval=COMMAND_WAKE_MIN_INTERVAL_SECONDS,
            summary=GROUP_SUMMARIES[group],
            state_model=GROUP_STATE_MODELS[group],
            retry=3,
            # Deliberately excludes bare TimeoutError. vito sets no explicit
            # timeout=, so cosalette's F-3 backstop equals the poll interval
            # (up to polling_system=3600s). Retrying a framework timeout would
            # burn interval-sized budgets (3x interval before the failure is
            # counted) on an already-wedged serial bus that will not self-heal
            # on an immediate retry. Let F-3 fail fast; OptolinkTimeoutError
            # still retries transient serial read timeouts.
            retry_on=(OptolinkConnectionError, OptolinkTimeoutError),
        )
    for group in COMMAND_GROUPS:
        app.add_command(
            name=group,
            func=make_command_handler(group),
            summary=COMMAND_SUMMARIES.get(
                group, f"Control {group} parameters via Optolink serial"
            ),
            payload_model=dict,
            # See COMMAND_TIMEOUT_SECONDS — the 30 s default is too tight for a
            # full-group schedule write queued behind a telemetry cycle.
            timeout=COMMAND_TIMEOUT_SECONDS,
            unavailable_on=(OptolinkConnectionError, OptolinkTimeoutError),
        )
    # No timeout=: legionella is a long-running device generator, not a
    # per-invocation handler, so cosalette's 30 s command backstop does not
    # wrap it. It manages its own ctx.commands() budgets (5 s / 60 s) and
    # runs a shutdown-safe restore so the boiler is never left at the
    # elevated setpoint; its writes are single-signal and protocol-atomic
    # (cap-ug0).
    app.add_device("legionella", legionella_device)
