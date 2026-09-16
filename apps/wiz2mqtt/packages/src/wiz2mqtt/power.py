"""Power-source belief computation for wiz2mqtt (ADR-007).

Pure domain logic: derives a three-value belief (``on``/``off``/``unknown``)
about whether a power source's circuit has mains power, and assembles the
retained ``wiz2mqtt/{source}/state`` payload. No cosalette imports — testable
as plain Python.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
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
    settings: Wiz2MqttSettings, config: PowerSourceConfig, state: SharedState
) -> dict[str, object]:
    """Build the retained ``wiz2mqtt/{source}/state`` payload for *config*.

    ``power_request`` stays ``None`` (omitted on the wire) until
    cap-bjw9.12 gives it meaning.
    """
    belief = belief_for_source(settings, state, config)
    state.source_belief[config.name] = belief
    return {
        "powered": belief,
        "power_request": None,
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
