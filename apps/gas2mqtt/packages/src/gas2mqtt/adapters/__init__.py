"""Hardware and infrastructure adapters for gas2mqtt."""

from gas2mqtt.adapters.fake import FakeMagnetometer, FakeStorage, NullStorage
from gas2mqtt.adapters.json_storage import JsonFileStorage
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter

__all__ = [
    "FakeMagnetometer",
    "FakeStorage",
    "JsonFileStorage",
    "NullStorage",
    "Qmc5883lAdapter",
]
