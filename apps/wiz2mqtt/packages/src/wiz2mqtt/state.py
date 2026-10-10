"""Shared per-bulb debounce state for wiz2mqtt.

Holds the dedup bookkeeping the per-bulb device tick
(:func:`wiz2mqtt.entity.bulb_entity_tick`) needs so it never re-publishes
identical retained ``state``/``availability`` messages every tick.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from wiz2mqtt.models import BulbState

if TYPE_CHECKING:
    from wiz2mqtt.intent import AppliedCommand, DesiredState, PendingCommand
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

    suppressed_desired_state_generation: dict[str, int] = field(default_factory=dict)
    """Desired states discarded with a queued command, keyed by generation.

    An on-to-off source signal can intentionally drop a pending command.  Its
    desired state must not be restored on the next reconnect, including from
    the telemetry-side store.  A later command advances the generation and
    supersedes this suppression without losing that newer intent.
    """

    bulb_answered: dict[str, bool] = field(default_factory=dict)
    """Whether the most recent poll/push for a bulb succeeded — the raw
    evidence :mod:`wiz2mqtt.power` aggregates into a source's belief."""

    stale_answers: set[str] = field(default_factory=set)
    """Bulbs whose last answer came before the last change of their source's
    signal (ADR-007 amendment 2026-09-19). Rule 1 of the belief ignores such
    an answer; the bulb's next successful read removes it again."""

    pending_commands: dict[str, PendingCommand] = field(default_factory=dict)
    """At most one queued command per bulb, set while the bulb cannot be
    reached (ADR-008 feature D); newer fields merge into older intent, with
    a later appearance update superseding queued OFF by turning the bulb on."""

    last_applied: dict[str, AppliedCommand] = field(default_factory=dict)
    """Each bulb's last return-path write and its read-back outcome
    (ADR-008), published as ``last_applied``. In memory only, so it is
    absent again after a restart."""

    restore_retry_cycles: dict[str, int] = field(default_factory=dict)
    """Exhausted return-path write/read-back cycles per bulb.

    Each cycle still has the three attempts required by ADR-008.  This
    separate counter bounds repeating an entirely unconfirmed cycle on later
    ticks without weakening those individual attempts.
    """

    restore_retry_at: dict[str, float] = field(default_factory=dict)
    """Monotonic earliest time for a bulb's next unconfirmed restore cycle."""

    restore_retry_exhausted: set[str] = field(default_factory=set)
    """Bulbs whose unconfirmed restore-cycle cap was reached.

    Their desired state remains authoritative, but no more writes occur until
    a new command resets the cap.
    """

    return_path_writing: set[str] = field(default_factory=set)
    """Bulbs whose return path is in its write-and-read-back loop. A command
    then queues, so the loop's next attempt cannot overwrite it (cap-8qjm)."""

    restore_settle_until: dict[str, float] = field(default_factory=dict)
    """Monotonic deadline of a confirmed return-path restore's settle window."""

    restore_settle_state: dict[str, BulbState] = field(default_factory=dict)
    """Read-back state confirmed by the return-path write, keyed by bulb."""

    boot_checks: set[str] = field(default_factory=set)
    """Bulbs whose firstBeat came while they still answered (cap-m6nh).

    Such a firstBeat can be a duplicate startup broadcast or a quick power
    cycle that missed no poll. The next successful read, forced past the
    cache, tells them apart: a bulb off its desired state re-arms reconnect.
    A failed read keeps the check pending.
    """

    boot_check_generation: dict[str, int] = field(default_factory=dict)
    """Latest firstBeat generation that still needs a post-event read."""

    source_belief: dict[str, Belief] = field(default_factory=dict)
    """Each power source's last-computed belief, refreshed by its own
    telemetry tick (:mod:`wiz2mqtt.power`)."""

    source_signal: dict[str, Signal | None] = field(default_factory=dict)
    """Each power source's last-known raw relay signal, set by the
    ``power_signal`` inbound handler from the subscribed ``signal_topic``."""

    source_signal_at: dict[str, float] = field(default_factory=dict)
    """Monotonic reading of each power source's last signal change, the start
    of its ``boot_grace`` window (:func:`wiz2mqtt.power.in_boot_grace`)."""

    source_power_on_requested: set[str] = field(default_factory=set)
    """Power sources with an outstanding power-on request (ADR-009).

    Latched by :func:`wiz2mqtt.power.note_command` when a command wants a
    dark circuit lit, and released by :func:`wiz2mqtt.power.power_request`
    once the belief becomes ``"on"`` or no member wants to be on any more.
    Empty at startup, so a retained ``on`` from a previous run is replaced
    by ``null`` on the source's first tick."""

    source_idle_since: dict[str, float] = field(default_factory=dict)
    """Monotonic reading at which every member of a power source became
    desired ``OFF`` (ADR-009), absent while a member wants to be on.

    The start of the ``power_off_idle_delay`` timer. It is set on a tick,
    never at startup, so a restart cannot cut a circuit before the delay
    has run once in this process."""

    boot_callback_registered: bool = False
    """Guards :meth:`wiz2mqtt.ports.WizBulbPort.register_boot_callback` being
    called exactly once app-wide, from whichever bulb ticks first."""
