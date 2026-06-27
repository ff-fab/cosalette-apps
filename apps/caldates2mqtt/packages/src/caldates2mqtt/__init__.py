"""caldates2mqtt — CalDAV calendar dates to MQTT bridge."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("caldates2mqtt")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
