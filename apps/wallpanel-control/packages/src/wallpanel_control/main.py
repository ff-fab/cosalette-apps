"""Entry point for wallpanel-control.

Composition root: wires cosalette App with SSH/WoL adapters and the
router modules for display and system actions.

Topic layout::

    wallpanel-control/display/set
        ← {"state": "on"|"off"}
        ← {"brightness_percent": <1-100>}
        ← {"state": "on", "brightness_percent": <1-100>}

    wallpanel-control/display/state
        → published once after each accepted display command, once at startup
          from the last saved answer, and by the panel probe when the observed
          reachability changes (app ADR-001)
        ← {"available": true, "state": "on"|"off", "brightness_percent": <int>}
        ← {"available": false, "state": null, "brightness_percent": null}

    wallpanel-control/system/action/set
        ← {"action": "wake"|"suspend"|"hibernate"}

    wallpanel-control/system/action/state
        ← {"accepted": bool, "action": "wake"|"suspend"|"hibernate",
           "observed": "pending"|"confirmed"|"timeout"|null}
"""

from __future__ import annotations

import cosalette

from wallpanel_control import __version__
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.adapters.ssh_adapter import SshWallpanel
from wallpanel_control.adapters.wol_adapter import UdpWol
from wallpanel_control.devices import display, probe, restore, system
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings


def _make_ssh_wallpanel(settings: WallpanelControlSettings) -> SshWallpanel:
    """Factory for the production SSH wallpanel adapter."""
    return SshWallpanel(settings)


# A rejected payload publishes error_type "validation". Under cosalette's legacy
# coupling (ADR-061) the map entry also publishes the message, which cosalette
# already sanitises to field locations and pydantic type codes, never the input.
# disclose_messages_for would fully define disclosure, forcing the framework's own
# mapped errors to be re-listed. Every other app error keeps the class name only.
ERROR_TYPE_MAP: dict[type[Exception], str] = {
    cosalette.PayloadValidationError: "validation",
}

app = cosalette.App(
    name="wallpanel-control",
    version=__version__,
    description="Wall panel display and system control via SSH",
    settings_class=WallpanelControlSettings,
    error_type_map=ERROR_TYPE_MAP,
    adapters={
        WallpanelPort: (_make_ssh_wallpanel, FakeWallpanel),
        WolPort: (UdpWol, FakeWol),
    },
    # Default JsonFileStore (ADR-049 static app — no config-removable
    # entities): kept for the runtime-discovery topic snapshot only, so
    # entities removed in a future release are cleared from Home Assistant
    # on the next startup (monorepo ADR-004).
    # No exit_after_stale/restart_on_stale (no telemetry or streams; root devices
    # derive no stale_after), no adapter
    # health_check (a sleeping panel is normal) and no redact= (no secrets reach
    # log text). See docs/configuration.md > Health and recovery.
)

# ADR-004: runtime HA discovery
app.discovery()

app.state(restore.create_last_answers)
app.include_router(display.router)
app.include_router(system.router)
app.include_router(probe.router)


def main() -> None:
    """Start the application, or answer a CLI flag such as ``--version``.

    ``cli()`` rather than ``run()``: ``run()`` ignores the command line, so
    ``--help``, ``--version``, ``--dry-run`` and ``--env-file`` would start
    the service instead.
    """
    app.cli()
