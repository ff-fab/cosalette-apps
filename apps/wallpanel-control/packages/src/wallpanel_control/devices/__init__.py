"""Device modules for wallpanel-control."""

import cosalette

# cosalette 0.11.2 has an import cycle: cosalette.Router() raises ImportError
# unless cosalette.App was resolved first, and the device modules build their
# routers at import time, so the app crashed on start. Resolving App here, before
# any device module loads, imports the cycle in the working order. Drop this once
# an upstream release fixes the cycle (cap-nycg).
cosalette.App  # noqa: B018
