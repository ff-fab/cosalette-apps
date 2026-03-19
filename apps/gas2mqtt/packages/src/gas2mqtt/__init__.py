"""gas2mqtt

An app to read a domestic gas meter using a digital magnetometer.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gas2mqtt")
except PackageNotFoundError:
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
