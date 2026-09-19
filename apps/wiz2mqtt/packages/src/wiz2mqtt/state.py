"""Shared per-bulb debounce state for wiz2mqtt.

Holds the dedup bookkeeping the per-bulb device tick
(:func:`wiz2mqtt.entity.bulb_entity_tick`) needs so it never re-publishes
identical retained ``state``/``availability`` messages every tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from wiz2mqtt.intent import DesiredState, PendingCommand
    from wiz2mqtt.power import Belief, Signal


@dataclass
class SharedState:
    """Per-bulb debounce state, keyed by bulb name.

    Telemetry and command handlers share this state: telemetry maintains
    readback and availability evidence, while commands update desired intent
    and pending work.
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

    phase: dict[str, Literal["steady", "reconnect"]] = field(default_factory=dict)
    """Per-bulb ADR-008 phase. Resolved lazily on a bulb's first tick from
    whether a desired state is already persisted, then advanced to
    ``"reconnect"`` on a boot event (cap-bjw9.4). Consumed by the ADR-008
    return path (cap-bjw9.8, entity.py's ``_run_return_path``), which
    always leaves it ``"steady"`` again before the tick returns."""

    desired_state: dict[str, DesiredState] = field(default_factory=dict)
    """Each bulb's current desired state (ADR-008) — the in-process source of
    truth. cosalette caches one ``DeviceStore`` per telemetry registration
    for the whole run, so a bulb's command-side and telemetry-side stores
    are separate objects that never see each other's writes without a
    restart; this dict is what lets a command and the next tick agree
    within one process. The device store (see :mod:`wiz2mqtt.intent`) is
    only what survives a restart."""

    desired_state_generation: dict[str, int] = field(default_factory=dict)
    """Per-bulb command generation, advanced before a desired-state mutation.

    A telemetry tick captures it before awaiting a hardware read and drops
    that readback when a newer command advanced the generation in the meantime.
    """

    bulb_answered: dict[str, bool] = field(default_factory=dict)
    """Whether the most recent poll/push for a bulb succeeded — the raw
    evidence :mod:`wiz2mqtt.power` aggregates into a source's belief."""

    pending_commands: dict[str, PendingCommand] = field(default_factory=dict)
    """At most one queued command per bulb, set while the bulb cannot be
    reached (ADR-008 feature D); the newest command replaces the older one."""

    source_belief: dict[str, Belief] = field(default_factory=dict)
    """Each power source's last-computed belief, refreshed by its own
    telemetry tick (:mod:`wiz2mqtt.power`)."""

    source_signal: dict[str, Signal | None] = field(default_factory=dict)
    """Each power source's last-known raw relay signal, set by the
    ``power_signal`` inbound handler from the subscribed ``signal_topic``."""

    boot_callback_registered: bool = False
    """Guards :meth:`wiz2mqtt.ports.WizBulbPort.register_boot_callback` being
    called exactly once app-wide, from whichever bulb ticks first."""
