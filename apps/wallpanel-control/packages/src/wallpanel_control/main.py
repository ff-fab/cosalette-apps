"""Entry point for wallpanel-control.

Composition root: wires cosalette App with SSH/WoL adapters and the
router modules for brightness, screen, power, and status.

Topic layout::

    wallpanel-control/brightness/set    ← integer 0-100
    wallpanel-control/brightness/state  ← {"brightness": <int 0-100>}
    wallpanel-control/screen/set        ← ON|OFF
    wallpanel-control/screen/state      ← {"state": "ON"|"OFF"}
    wallpanel-control/power/set         ← OFF|SLEEP|WAKE
    wallpanel-control/power/state       ← {"state": "hibernating"|"suspended"|"waking"}
    wallpanel-control/status/state      ← {"available": bool, "brightness": int|null, "screen": str|null}
"""

from __future__ import annotations

import cosalette

from wallpanel_control import __version__
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.adapters.ssh_adapter import SshWallpanel
from wallpanel_control.adapters.wol_adapter import UdpWol
from wallpanel_control.devices import brightness, power, screen, status
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings


def _make_ssh_wallpanel(settings: WallpanelControlSettings) -> SshWallpanel:
    """Factory for the production SSH wallpanel adapter."""
    return SshWallpanel(settings)


app = cosalette.App(
    name="wallpanel-control",
    version=__version__,
    description="Wall panel brightness, screen and power control via SSH",
    settings_class=WallpanelControlSettings,
    adapters={
        WallpanelPort: (_make_ssh_wallpanel, FakeWallpanel),
        WolPort: (UdpWol, FakeWol),
    },
)

app.include_router(brightness.router)
app.include_router(screen.router)
app.include_router(power.router)
app.include_router(status.router)


def main() -> None:
    """Start the application."""
    app.run()
