"""Entry point for wallpanel-control.

Composition root: wires cosalette App with SSH/WoL adapters and the
router modules for display and system actions.

Topic layout::

    wallpanel-control/display/set
        ← {"state": "on"|"off"}
        ← {"brightness_percent": <1-100>}
        ← {"state": "on", "brightness_percent": <1-100>}

    wallpanel-control/display/state
        → published once after each accepted display command
        ← {"available": true, "state": "on"|"off", "brightness_percent": <int>}
        ← {"available": false, "state": null, "brightness_percent": null}

    wallpanel-control/system/action/set
        ← {"action": "wake"|"suspend"|"hibernate"}

    wallpanel-control/system/action/state
        ← {"accepted": bool, "action": "wake"|"suspend"|"hibernate"}
"""

from __future__ import annotations

import cosalette

from wallpanel_control import __version__
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.adapters.ssh_adapter import SshWallpanel
from wallpanel_control.adapters.wol_adapter import UdpWol
from wallpanel_control.devices import display, system
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings


def _make_ssh_wallpanel(settings: WallpanelControlSettings) -> SshWallpanel:
    """Factory for the production SSH wallpanel adapter."""
    return SshWallpanel(settings)


app = cosalette.App(
    name="wallpanel-control",
    version=__version__,
    description="Wall panel display and system control via SSH",
    settings_class=WallpanelControlSettings,
    adapters={
        WallpanelPort: (_make_ssh_wallpanel, FakeWallpanel),
        WolPort: (UdpWol, FakeWol),
    },
)

app.include_router(display.router)
app.include_router(system.router)


def main() -> None:
    """Start the application."""
    app.run()
