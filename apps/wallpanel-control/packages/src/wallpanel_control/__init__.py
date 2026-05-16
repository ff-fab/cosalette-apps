"""wallpanel-control — MQTT bridge for wall-panel display and system control via SSH and Wake-on-LAN."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wallpanel-control")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
