"""Unit tests for power.py — power-source belief computation (ADR-007).

Test Techniques Used:
- Decision Table: the three belief rules, in priority order
- Equivalence Partitioning: signal present/absent × when_unreachable
- Boundary Value Analysis: exactly one of several members answering
- Specification-based: the retained source payload shape
"""

from __future__ import annotations

import pytest

from tests.fixtures.settings import build_settings
from wiz2mqtt.intent import Appearance, DesiredState
from wiz2mqtt.models import POWER_REQUEST_INACTIVE
from wiz2mqtt.power import (
    belief_for_bulb,
    belief_for_source,
    compute_belief,
    note_command,
    parse_signal,
    power_request,
    record_signal,
    signal_wake_targets,
    source_for_signal_topic,
    source_payload,
)
from wiz2mqtt.settings import Wiz2MqttSettings
from wiz2mqtt.state import SharedState

_UNCONFIGURED = {"_env_file": None, "_config_file": None}


class TestComputeBelief:
    """The three belief rules, in priority order (ADR-007)."""

    def test_rule1_one_answering_member_and_signal_off_gives_on(self) -> None:
        """Evidence outranks a contradicting signal."""
        assert (
            compute_belief(
                any_member_answered=True, signal="off", when_unreachable="fault"
            )
            == "on"
        )

    def test_rule1_one_answering_member_and_no_signal_gives_on(self) -> None:
        assert (
            compute_belief(
                any_member_answered=True, signal=None, when_unreachable="fault"
            )
            == "on"
        )

    def test_rule2_no_answering_member_and_signal_on_gives_on(self) -> None:
        assert (
            compute_belief(
                any_member_answered=False, signal="on", when_unreachable="fault"
            )
            == "on"
        )

    def test_rule2_no_answering_member_and_signal_off_gives_off(self) -> None:
        assert (
            compute_belief(
                any_member_answered=False, signal="off", when_unreachable="fault"
            )
            == "off"
        )

    def test_rule3_no_evidence_gives_unknown_for_fault(self) -> None:
        assert (
            compute_belief(
                any_member_answered=False, signal=None, when_unreachable="fault"
            )
            == "unknown"
        )

    def test_rule3_no_evidence_gives_off_for_no_power(self) -> None:
        assert (
            compute_belief(
                any_member_answered=False, signal=None, when_unreachable="no_power"
            )
            == "off"
        )


class TestBeliefForBulb:
    """The per-bulb lookup used by ``bulb_entity_tick`` and ``bulb_set``."""

    def test_none_when_bulb_has_no_power_source(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}], **_UNCONFIGURED
        )
        assert belief_for_bulb(settings, SharedState(), "desk") is None

    def test_on_when_the_bulb_itself_answered(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
            power_sources=[{"name": "p", "members": ["desk"]}],
            **_UNCONFIGURED,
        )
        state = SharedState()
        state.bulb_answered["desk"] = True

        assert belief_for_bulb(settings, state, "desk") == "on"

    def test_on_when_a_sibling_member_answered(self) -> None:
        """Technique: Boundary Value Analysis — evidence from a peer, not self."""
        settings = Wiz2MqttSettings(
            bulbs=[
                {"name": "desk", "ip": "10.0.0.1"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            power_sources=[{"name": "p", "members": ["desk", "lamp"]}],
            **_UNCONFIGURED,
        )
        state = SharedState()
        state.bulb_answered["lamp"] = True

        assert belief_for_bulb(settings, state, "desk") == "on"

    def test_off_when_source_signal_is_off_and_no_one_answers(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
            power_sources=[{"name": "p", "members": ["desk"]}],
            **_UNCONFIGURED,
        )
        state = SharedState()
        state.source_signal["p"] = "off"

        assert belief_for_bulb(settings, state, "desk") == "off"


class TestSourcePayload:
    """The retained ``wiz2mqtt/{source}/state`` payload (ADR-007 amendment)."""

    def test_payload_shape_and_belief(self) -> None:
        settings = Wiz2MqttSettings(
            bulbs=[
                {"name": "desk", "ip": "10.0.0.1"},
                {"name": "lamp", "ip": "10.0.0.2"},
            ],
            power_sources=[{"name": "p", "members": ["desk", "lamp"]}],
            **_UNCONFIGURED,
        )
        state = SharedState()
        state.bulb_answered["desk"] = True

        payload = source_payload(settings, settings.power_sources[0], state, 0.0)

        assert payload == {
            "powered": "on",
            "power_request": "__inactive__",
            "members": ["desk", "lamp"],
        }

    def test_payload_records_the_belief_on_shared_state(self) -> None:
        """The source's own tick caches its belief for cap-bjw9.6's bulb_set lookup."""
        settings = Wiz2MqttSettings(
            bulbs=[{"name": "desk", "ip": "10.0.0.1"}],
            power_sources=[{"name": "p", "members": ["desk"]}],
            **_UNCONFIGURED,
        )
        state = SharedState()

        source_payload(settings, settings.power_sources[0], state, 0.0)

        assert state.source_belief["p"] == "unknown"


@pytest.mark.parametrize(
    ("any_member_answered", "signal", "when_unreachable", "expected"),
    [
        (True, "on", "fault", "on"),
        (True, "off", "no_power", "on"),
        (False, "on", "no_power", "on"),
        (False, "off", "fault", "off"),
        (False, None, "fault", "unknown"),
        (False, None, "no_power", "off"),
    ],
)
def test_belief_truth_table(
    any_member_answered: bool,
    signal: str | None,
    when_unreachable: str,
    expected: str,
) -> None:
    """Technique: Decision Table — the full 3-rule matrix in one parametrised sweep."""
    assert (
        compute_belief(
            any_member_answered=any_member_answered,
            signal=signal,  # type: ignore[arg-type]
            when_unreachable=when_unreachable,  # type: ignore[arg-type]
        )
        == expected
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("on", "on"),
        ("off", "off"),
        ("  on\n", "on"),
        ("\toff ", "off"),
        ("ON", None),
        ("Off", None),
        ("true", None),
        ("1", None),
        ("", None),
        ("   ", None),
        ("on off", None),
        ('{"state": "on"}', None),
    ],
)
def test_parse_signal(payload: str, expected: str | None) -> None:
    """Technique: Equivalence Partitioning — accepted, whitespace-padded, rejected.

    ADR-007: only lowercase ``on``/``off`` after one trim is a signal.
    """
    assert parse_signal(payload) == expected


class TestSourceForSignalTopic:
    """A signal topic resolves to the one source that subscribes to it."""

    @staticmethod
    def _settings() -> Wiz2MqttSettings:
        return build_settings(
            [{"name": "a", "ip": "10.0.0.1"}, {"name": "b", "ip": "10.0.0.2"}],
            [
                {"name": "up", "members": ["a"], "signal_topic": "relay/up"},
                {"name": "down", "members": ["b"]},
            ],
        )

    def test_returns_the_source_that_declares_the_topic(self) -> None:
        """Technique: Specification-based — an exact topic match."""
        source = source_for_signal_topic(self._settings(), "relay/up")

        assert source is not None
        assert source.name == "up"

    @pytest.mark.parametrize("topic", ["relay/other", "relay/up/extra", "down", ""])
    def test_returns_none_for_a_topic_no_source_declares(self, topic: str) -> None:
        """Technique: Equivalence Partitioning — near misses and a source name.

        ``down`` has no ``signal_topic``, so neither its name nor an empty
        topic may resolve to it.
        """
        assert source_for_signal_topic(self._settings(), topic) is None


class TestRecordSignal:
    """The stored signal changes only when the new one differs."""

    def test_first_signal_is_stored_as_a_change(self) -> None:
        """Technique: State Transition — no signal to on."""
        state = SharedState()

        assert record_signal(state, "up", "on") is True
        assert state.source_signal == {"up": "on"}

    def test_repeated_signal_is_not_a_change(self) -> None:
        """Technique: State Transition — on to on."""
        state = SharedState()
        record_signal(state, "up", "on")

        assert record_signal(state, "up", "on") is False

    def test_opposite_signal_replaces_the_stored_one(self) -> None:
        """Technique: State Transition — on to off."""
        state = SharedState()
        record_signal(state, "up", "on")

        assert record_signal(state, "up", "off") is True
        assert state.source_signal == {"up": "off"}


def test_signal_wake_targets_lists_the_source_then_its_sorted_bulbs() -> None:
    """Technique: Specification-based — a change arms the source and its members."""
    settings = build_settings(
        [{"name": "b", "ip": "10.0.0.2"}, {"name": "a", "ip": "10.0.0.1"}],
        [{"name": "up", "members": ["b", "a"]}],
    )

    assert signal_wake_targets(settings, "up") == ["up", "a", "b"]


# ---------------------------------------------------------------------------
# Power requests (ADR-009, cap-bjw9.12)
# ---------------------------------------------------------------------------

_IDLE_DELAY = 600.0


def _request_settings(**source_keys: object) -> Wiz2MqttSettings:
    """Two bulbs on one power source carrying *source_keys*."""
    return build_settings(
        [{"name": "desk", "ip": "10.0.0.1"}, {"name": "lamp", "ip": "10.0.0.2"}],
        [{"name": "p", "members": ["desk", "lamp"], **source_keys}],
    )


def _desire(state: SharedState, name: str, value: str) -> None:
    """Record *name*'s desired state without going through a command."""
    state.desired_state[name] = DesiredState(
        state="ON" if value == "ON" else "OFF",
        appearance=Appearance(
            brightness=None,
            hue=None,
            saturation=None,
            color_temp_kelvin=None,
            scene=None,
            speed=None,
        ),
        writer="command",
        written_at=0.0,
    )


def _request(settings: Wiz2MqttSettings, state: SharedState, now: float) -> object:
    """The request of the single source of *settings* at *now*."""
    source = settings.power_sources[0]
    return power_request(
        settings, source, state, belief_for_source(settings, state, source), now
    )


class TestPowerOnRequest:
    """A command for a dark circuit asks for power (ADR-009, feature C)."""

    def test_command_on_a_dark_circuit_raises_the_request(self) -> None:
        """Technique: Decision Table — belief off x opt-in x desired ON."""
        settings = _request_settings(
            when_unreachable="no_power", enable_power_on_request=True
        )
        state = SharedState()

        assert note_command(settings, state, "desk", desired_on=True) == "p"
        _desire(state, "desk", "ON")

        assert _request(settings, state, 0.0) == "on"

    def test_opt_out_publishes_no_request(self) -> None:
        """Technique: Decision Table — the same command without the opt-in."""
        settings = _request_settings(when_unreachable="no_power")
        state = SharedState()

        note_command(settings, state, "desk", desired_on=True)
        _desire(state, "desk", "ON")

        assert _request(settings, state, 0.0) == POWER_REQUEST_INACTIVE

    def test_command_wanting_darkness_wakes_its_source(self) -> None:
        """Technique: Decision Table — OFF can clear a retained request promptly."""
        settings = _request_settings(
            when_unreachable="no_power", enable_power_on_request=True
        )
        state = SharedState()

        assert note_command(settings, state, "desk", desired_on=False) == "p"
        assert state.source_power_on_requested == set()

    def test_command_for_a_bulb_without_a_source_arms_nothing(self) -> None:
        """Technique: Equivalence Partitioning — a bulb outside every source."""
        settings = build_settings([{"name": "desk", "ip": "10.0.0.1"}])
        state = SharedState()

        assert note_command(settings, state, "desk", desired_on=True) is None

    def test_request_clears_when_the_belief_becomes_on(self) -> None:
        """Technique: State Transition — observed convergence releases the latch."""
        settings = _request_settings(
            when_unreachable="no_power", enable_power_on_request=True
        )
        state = SharedState()
        note_command(settings, state, "desk", desired_on=True)
        _desire(state, "desk", "ON")

        state.bulb_answered["desk"] = True

        assert _request(settings, state, 0.0) == POWER_REQUEST_INACTIVE
        assert state.source_power_on_requested == set()

    def test_request_survives_a_circuit_that_stays_dark(self) -> None:
        """Technique: Specification-based — never cleared on a timeout."""
        settings = _request_settings(
            when_unreachable="no_power", enable_power_on_request=True
        )
        state = SharedState()
        note_command(settings, state, "desk", desired_on=True)
        _desire(state, "desk", "ON")

        assert _request(settings, state, 86400.0) == "on"

    def test_request_clears_when_no_member_wants_light_any_more(self) -> None:
        """Technique: State Transition — an unknown peer does not retain it."""
        settings = _request_settings(
            when_unreachable="no_power", enable_power_on_request=True
        )
        state = SharedState()
        note_command(settings, state, "desk", desired_on=True)
        _desire(state, "desk", "OFF")

        assert _request(settings, state, 0.0) == POWER_REQUEST_INACTIVE


class TestPowerOffRequest:
    """An idle wiz_bulbs_only circuit may be cut (ADR-009, feature C)."""

    @staticmethod
    def _idle_settings(**overrides: object) -> Wiz2MqttSettings:
        return _request_settings(
            signal_topic="relay/state",
            enable_power_off_request=True,
            wiz_bulbs_only=True,
            power_off_idle_delay=_IDLE_DELAY,
            **overrides,
        )

    @staticmethod
    def _all_off(settings: Wiz2MqttSettings) -> SharedState:
        """Both members desired OFF on a circuit the signal reports powered."""
        state = SharedState()
        state.source_signal["p"] = "on"
        _desire(state, "desk", "OFF")
        _desire(state, "lamp", "OFF")
        return state

    def test_no_request_before_the_delay_elapses(self) -> None:
        """Technique: Boundary Value Analysis — one second short of the delay."""
        settings = self._idle_settings()
        state = self._all_off(settings)

        assert _request(settings, state, 0.0) == POWER_REQUEST_INACTIVE
        assert _request(settings, state, _IDLE_DELAY - 1.0) == POWER_REQUEST_INACTIVE

    def test_request_fires_once_the_delay_elapses(self) -> None:
        """Technique: Boundary Value Analysis — exactly at the delay."""
        settings = self._idle_settings()
        state = self._all_off(settings)
        _request(settings, state, 0.0)

        assert _request(settings, state, _IDLE_DELAY) == "off"

    def test_one_member_on_cancels_the_timer(self) -> None:
        """Technique: State Transition — a command for light restarts the wait."""
        settings = self._idle_settings()
        state = self._all_off(settings)
        _request(settings, state, 0.0)

        _desire(state, "lamp", "ON")
        assert _request(settings, state, _IDLE_DELAY) == POWER_REQUEST_INACTIVE

        _desire(state, "lamp", "OFF")
        assert _request(settings, state, _IDLE_DELAY) == POWER_REQUEST_INACTIVE
        assert _request(settings, state, 2 * _IDLE_DELAY) == "off"

    def test_a_command_for_light_cancels_the_timer_and_asks_for_power(self) -> None:
        """Technique: Decision Table — both directions enabled on one source."""
        settings = self._idle_settings(
            enable_power_on_request=True, when_unreachable="no_power"
        )
        state = self._all_off(settings)
        state.source_signal["p"] = "off"
        _request(settings, state, 0.0)

        assert note_command(settings, state, "lamp", desired_on=True) == "p"
        _desire(state, "lamp", "ON")

        assert "p" not in state.source_idle_since
        assert _request(settings, state, _IDLE_DELAY) == "on"

    def test_request_clears_when_the_belief_becomes_off(self) -> None:
        """Technique: State Transition — observed convergence ends the request."""
        settings = self._idle_settings()
        state = self._all_off(settings)
        _request(settings, state, 0.0)
        assert _request(settings, state, _IDLE_DELAY) == "off"

        state.source_signal["p"] = "off"

        assert _request(settings, state, _IDLE_DELAY) == POWER_REQUEST_INACTIVE

    def test_opt_out_publishes_no_request(self) -> None:
        """Technique: Decision Table — the same idle circuit without the opt-in."""
        settings = _request_settings(signal_topic="relay/state")
        state = self._all_off(settings)
        _request(settings, state, 0.0)

        assert _request(settings, state, 2 * _IDLE_DELAY) == POWER_REQUEST_INACTIVE

    def test_a_member_with_no_known_intent_is_never_idle(self) -> None:
        """Technique: Error Guessing — silence is not evidence a circuit may be cut."""
        settings = self._idle_settings()
        state = SharedState()
        state.source_signal["p"] = "on"
        _desire(state, "desk", "OFF")

        assert _request(settings, state, 0.0) == POWER_REQUEST_INACTIVE
        assert _request(settings, state, 2 * _IDLE_DELAY) == POWER_REQUEST_INACTIVE

    def test_a_restart_never_cuts_a_circuit_on_the_first_tick(self) -> None:
        """Technique: Specification-based — the timer starts in this process.

        A restart reloads a desired ``OFF`` that is hours old, and the wall
        clock is far past any previous timer. The first tick must still
        publish nothing.
        """
        settings = self._idle_settings()
        state = self._all_off(settings)

        assert _request(settings, state, 1.0e9) == POWER_REQUEST_INACTIVE

    def test_a_source_with_no_member_is_never_idle(self) -> None:
        """Technique: Boundary Value Analysis — an empty member list."""
        settings = build_settings(
            [{"name": "desk", "ip": "10.0.0.1", "power_source": "other"}],
            [
                {"name": "other", "members": ["desk"]},
                {
                    "name": "p",
                    "members": ["desk"],
                    "signal_topic": "relay/state",
                    "enable_power_off_request": True,
                    "wiz_bulbs_only": True,
                },
            ],
        )
        state = SharedState()
        state.source_signal["p"] = "on"
        _desire(state, "desk", "OFF")
        source = settings.power_sources[1]

        assert settings.bulbs_for_power_source("p") == []
        assert power_request(settings, source, state, "on", 0.0) == (
            POWER_REQUEST_INACTIVE
        )
        assert power_request(settings, source, state, "on", 2 * _IDLE_DELAY) == (
            POWER_REQUEST_INACTIVE
        )
