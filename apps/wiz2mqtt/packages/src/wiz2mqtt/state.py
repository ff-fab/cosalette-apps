"""Shared per-bulb debounce state for wiz2mqtt (cap-10u.13).

Holds the dedup bookkeeping the per-bulb device tick
(:func:`wiz2mqtt.entity.bulb_entity_tick`) needs so it never re-publishes
identical retained ``state``/``availability`` messages every tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SharedState:
    """Per-bulb debounce state, keyed by bulb name.

    Owned exclusively by :func:`wiz2mqtt.entity.bulb_entity_tick`.
    """

    consecutive_failures: dict[str, int] = field(default_factory=dict)
    """Consecutive failed polls per bulb; reset to 0 on any successful poll."""

    last_availability: dict[str, Literal["online", "offline"]] = field(
        default_factory=dict
    )
    """Last published availability per bulb (``"online"``/``"offline"``).

    State-payload dedup itself doesn't need a matching field here — the
    ``@app.telemetry`` runner tracks each bulb's last-published payload
    internally for its ``publish=OnChange()`` strategy.
    """
