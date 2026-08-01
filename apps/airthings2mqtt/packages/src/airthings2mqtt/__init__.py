"""airthings2mqtt — Reads Airthings Wave sensors over BLE, publishes to MQTT."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("airthings2mqtt")
except PackageNotFoundError:  # pragma: no cover
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
