"""jeelink2mqtt

A smart home app to read in values of Jeelink temperature and humidity sensors.
"""

from importlib.metadata import PackageNotFoundError, version

from jeelink2mqtt.models import (
    MappingEvent,
    SensorConfig,
    SensorMapping,
    SensorReading,
)
from jeelink2mqtt.settings import Jeelink2MqttSettings

try:
    # Prefer the generated version file (setuptools_scm at build time)
    from ._version import __version__
except ImportError:
    try:
        # Fallback to installed package metadata
        __version__ = version("jeelink2mqtt")
    except PackageNotFoundError:
        # Last resort fallback for editable installs without metadata
        __version__ = "0.0.0+unknown"

__all__ = [
    "Jeelink2MqttSettings",
    "MappingEvent",
    "SensorConfig",
    "SensorMapping",
    "SensorReading",
    "__version__",
]
