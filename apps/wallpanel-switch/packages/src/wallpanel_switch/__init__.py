"""wallpanel-switch — Wall panel brightness, screen and power control via SSH."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wallpanel-switch")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
