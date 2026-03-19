"""Hardware and infrastructure adapters for gas2mqtt."""

from gas2mqtt.adapters.fake import FakeMagnetometer
from gas2mqtt.adapters.qmc5883l import Qmc5883lAdapter

__all__ = [
    "FakeMagnetometer",
    "Qmc5883lAdapter",
]
