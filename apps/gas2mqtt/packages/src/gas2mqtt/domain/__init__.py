"""Pure domain logic for gas2mqtt.

Contains stateless/stateful domain objects with no I/O dependencies:
- SchmittTrigger: Detects gas meter rotations from magnetic field
- EwmaFilter: Exponentially weighted moving average for temperature
- ConsumptionTracker: Tracks gas consumption in m³
"""

from gas2mqtt.domain.consumption import ConsumptionTracker
from gas2mqtt.domain.ewma import EwmaFilter
from gas2mqtt.domain.schmitt import SchmittTrigger, TriggerEvent, TriggerState

__all__ = [
    "ConsumptionTracker",
    "EwmaFilter",
    "SchmittTrigger",
    "TriggerEvent",
    "TriggerState",
]
