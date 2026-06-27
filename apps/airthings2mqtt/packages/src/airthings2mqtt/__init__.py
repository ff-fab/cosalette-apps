"""airthings2mqtt — Reads Airthings Wave air quality sensors over BLE and publishes temperature, humidity, and radon data to MQTT."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("airthings2mqtt")
except PackageNotFoundError:
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
