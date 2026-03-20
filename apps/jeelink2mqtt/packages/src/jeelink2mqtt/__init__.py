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
    __version__ = version("jeelink2mqtt")
except PackageNotFoundError:
    # Fallback for editable installs without metadata
    __version__ = "0.0.0+unknown"

__all__ = [
    "Jeelink2MqttSettings",
    "MappingEvent",
    "SensorConfig",
    "SensorMapping",
    "SensorReading",
    "__version__",
]
