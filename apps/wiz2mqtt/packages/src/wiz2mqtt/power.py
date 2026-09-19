"""Power-source belief computation for wiz2mqtt (ADR-007).

Pure domain logic: derives a three-value belief (``on``/``off``/``unknown``)
about whether a power source's circuit has mains power, and assembles the
retained ``wiz2mqtt/{source}/state`` payload. No cosalette imports — testable
as plain Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from wiz2mqtt.models import POWER_REQUEST_INACTIVE

if TYPE_CHECKING:
    from wiz2mqtt.models import PowerRequestWire
    from wiz2mqtt.settings import PowerSourceConfig, Wiz2MqttSettings
    from wiz2mqtt.state import SharedState

Belief = Literal["on", "off", "unknown"]
Signal = Literal["on", "off"]


def compute_belief(
    *,
    any_member_answered: bool,
    signal: Signal | None,
    when_unreachable: Literal["fault", "no_power"],
) -> Belief:
    """Derive the belief of one power source (ADR-007, three rules in order).

    1. If a minimum of one member bulb answers, the belief is ``"on"``.
       Evidence outranks the signal.
    2. If no bulb answers and a signal exists, the belief is the signal.
    3. If no bulb answers and no signal exists, the belief is ``"unknown"``
       for a ``"fault"`` source, ``"off"`` for a ``"no_power"`` source —
       ``when_unreachable`` is the tie-break with no better evidence.
    """
    if any_member_answered:
        return "on"
    if signal is not None:
        return signal
    return "unknown" if when_unreachable == "fault" else "off"


def parse_signal(payload: str) -> Signal | None:
    """Parse a relay ``signal_topic`` payload (ADR-007 signal contract).

    Accepts only lowercase ``on`` or ``off`` after one whitespace trim. Any
    other payload returns ``None``, so the belief stays unchanged.
    """
    match payload.strip():
        case "on":
            return "on"
        case "off":
            return "off"
        case _:
            return None


def source_for_signal_topic(
    settings: Wiz2MqttSettings, topic: str
) -> PowerSourceConfig | None:
    """Return the power source that subscribes to *topic*, if any.

    ``signal_topic`` is unique per source (validated by the settings).
    """
    return next(
        (source for source in settings.power_sources if source.signal_topic == topic),
        None,
    )


def record_signal(state: SharedState, source_name: str, signal: Signal) -> bool:
    """Store *signal* for *source_name*; return whether it differs from the last.

    A repeat of the stored signal changes no belief, so the caller can skip
    waking the source and its bulbs.
    """
    if state.source_signal.get(source_name) == signal:
        return False
    state.source_signal[source_name] = signal
    return True


def signal_wake_targets(settings: Wiz2MqttSettings, source_name: str) -> list[str]:
    """Return the entities a signal change arms: the source, then its bulbs."""
    return [source_name, *settings.bulbs_for_power_source(source_name)]


def belief_for_bulb(
    settings: Wiz2MqttSettings, state: SharedState, bulb_name: str
) -> Belief | None:
    """Return the current belief for *bulb_name*'s power source, if any.

    ``None`` means the bulb belongs to no power source — distinct from
    ``"unknown"``, though both render as JSON ``null`` on the bulb payload
    (ADR-001 amendment).
    """
    source = settings.power_source_of(bulb_name)
    if source is None:
        return None
    return belief_for_source(settings, state, source)


def source_payload(
    settings: Wiz2MqttSettings,
    config: PowerSourceConfig,
    state: SharedState,
    now: float,
) -> dict[str, object]:
    """Build the retained ``wiz2mqtt/{source}/state`` payload for *config*.

    *now* is a monotonic reading the caller takes, so the idle timer of
    :func:`power_request` is testable with plain floats.
    """
    belief = belief_for_source(settings, state, config)
    state.source_belief[config.name] = belief
    return {
        "powered": belief,
        "power_request": power_request(settings, config, state, belief, now),
        "members": settings.bulbs_for_power_source(config.name),
    }


def belief_for_source(
    settings: Wiz2MqttSettings, state: SharedState, source: PowerSourceConfig
) -> Belief:
    """Return the current belief of *source*, given today's evidence.

    Unlike :func:`belief_for_bulb`, always returns a concrete
    :data:`Belief` — the caller already has a resolved
    :class:`~wiz2mqtt.settings.PowerSourceConfig`, so there is no "no
    source" case to represent as ``None``.
    """
    members = settings.bulbs_for_power_source(source.name)
    any_member_answered = any(state.bulb_answered.get(m, False) for m in members)
    signal = state.source_signal.get(source.name)
    return compute_belief(
        any_member_answered=any_member_answered,
        signal=signal,
        when_unreachable=source.when_unreachable,
    )


# ---------------------------------------------------------------------------
# Power requests (ADR-009, cap-bjw9.12)
# ---------------------------------------------------------------------------


def note_command(
    settings: Wiz2MqttSettings, state: SharedState, bulb_name: str, *, desired_on: bool
) -> str | None:
    """Feed an accepted bulb command into its source's power request (ADR-009).

    Returns the name of the power source whose entity the caller must arm,
    or ``None`` when *bulb_name* has no source or nothing can change yet.

    A command that wants light cancels the idle timer of the source, and,
    on a dark circuit whose operator enabled power-on requests, latches a
    power-on request. A command that wants darkness changes no request now,
    but still returns its source so the caller promptly republishes any
    retained request that the new intent clears.

    "Dark" is the belief ``"off"`` alone, never ``"unknown"`` (ADR-009
    amendment 2026-09-14). An ``"unknown"`` source is a ``fault`` source
    with no signal and no answering member, so asking for power there
    would act on an absence of evidence.
    """
    source = settings.power_source_of(bulb_name)
    if source is None:
        return None
    if not desired_on:
        return source.name
    state.source_idle_since.pop(source.name, None)
    if (
        source.enable_power_on_request
        and belief_for_source(settings, state, source) == "off"
    ):
        state.source_power_on_requested.add(source.name)
    return source.name


def power_request(
    settings: Wiz2MqttSettings,
    config: PowerSourceConfig,
    state: SharedState,
    belief: Belief,
    now: float,
) -> PowerRequestWire:
    """The retained desired power state of *config* (ADR-009).

    ``"on"`` while a latched power-on request waits for the circuit,
    ``"off"`` while an idle ``wiz_bulbs_only`` circuit may be cut, and
    :data:`~wiz2mqtt.models.POWER_REQUEST_INACTIVE` (JSON ``null``)
    otherwise.

    A power-on request is raised by :func:`note_command` only, never by a
    read, a boot event or a signal. It is released here on convergence
    (the belief becomes ``"on"``) or when it becomes inapplicable (no
    member wants to be on any more), never on a timeout: a relay that
    takes a minute to react must still see it.

    A power-off request needs both operator opt-ins and a member list, and
    it is released as soon as the belief becomes ``"off"``. Power-on latch
    clearing only needs to know whether any member still wants light;
    power-off eligibility deliberately requires every member's known intent
    to be ``OFF``.
    """
    any_member_desired_on = _any_member_desired_on(settings, state, config.name)
    idle = _all_members_desired_off(settings, state, config.name)
    if belief == "on" or not any_member_desired_on:
        state.source_power_on_requested.discard(config.name)
    if config.name in state.source_power_on_requested:
        return "on"
    if belief != "off" and _idle_delay_elapsed(config, state, idle, now):
        return "off"
    return POWER_REQUEST_INACTIVE


def _all_members_desired_off(
    settings: Wiz2MqttSettings, state: SharedState, source_name: str
) -> bool:
    """Whether every member of *source_name* has a desired state of ``OFF``.

    A source with no member, or a member whose intent this process has not
    seen yet, is never idle — silence is not evidence that a circuit may
    be cut.
    """
    members = settings.bulbs_for_power_source(source_name)
    if not members:
        return False
    return all(
        (desired := state.desired_state.get(member)) is not None
        and desired.state == "OFF"
        for member in members
    )


def _any_member_desired_on(
    settings: Wiz2MqttSettings, state: SharedState, source_name: str
) -> bool:
    """Whether at least one member of *source_name* currently wants ``ON``."""
    return any(
        (desired := state.desired_state.get(member)) is not None
        and desired.state == "ON"
        for member in settings.bulbs_for_power_source(source_name)
    )


def _idle_delay_elapsed(
    config: PowerSourceConfig, state: SharedState, idle: bool, now: float
) -> bool:
    """Run the ``power_off_idle_delay`` timer of *config* and report expiry.

    Starts the timer on the first tick that finds the source idle, so a
    restart always spends the full delay in this process before a circuit
    can be cut. A member that wants to be on clears it again.
    """
    if not idle or not (config.enable_power_off_request and config.wiz_bulbs_only):
        state.source_idle_since.pop(config.name, None)
        return False
    return now - state.source_idle_since.setdefault(config.name, now) >= (
        config.power_off_idle_delay
    )
