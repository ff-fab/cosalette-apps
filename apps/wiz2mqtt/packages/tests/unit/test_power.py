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
from wiz2mqtt.power import (
    belief_for_bulb,
    compute_belief,
    parse_signal,
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

        payload = source_payload(settings, settings.power_sources[0], state)

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

        source_payload(settings, settings.power_sources[0], state)

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
