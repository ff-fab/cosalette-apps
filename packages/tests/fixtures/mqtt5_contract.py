"""The MQTT 5 retained-expiry contract, shared by every app that opts in.

Each app's ``packages/tests/integration/test_mqtt5_expiry.py`` supplies two
fixtures, ``mqtt5`` and ``mqtt311``, that run the app's real wiring against
:class:`mqtt5_broker.FakeMqtt5Broker`, and subclasses the two classes below.
The assertions live here once because the contract is one thing: what the
broker sees is decided by cosalette, and the apps only choose whether to opt in
(ADR-009).

Test Techniques Used:
- Specification-based: the opt-in stamps every retained publish and leaves
  non-retained publishes alone; the 3.1.1 wire stays unchanged.
- State Transition: virtual time crosses several ``expiry / 3`` windows; each
  retained topic is republished once per window and never ages out.
- Equivalence Partitioning: MQTT 5 opt-in versus the MQTT 3.1.1 default.
- Error Guessing: a refresh replays the last payload byte for byte, so a
  consumer that reacts to message receipt sees one duplicate per window.
"""

from __future__ import annotations

import aiomqtt
from mqtt5_broker import Observation

EXPIRY_SECONDS = 3
"""Smallest interval cosalette accepts; the refresh window is one second."""
WINDOWS = 3
"""Refresh windows an observation spans: more than one full expiry span."""


class Mqtt5Contract:
    """MQTT 5 opt-in: expiry on every retained topic, kept alive by refresh."""

    state_topic: str

    def test_connects_with_mqtt5(self, mqtt5: Observation) -> None:
        """Technique: Specification-based - the CONNECT requests protocol level 5."""
        assert mqtt5.broker.connects[0]["protocol"] == aiomqtt.ProtocolVersion.V5

    def test_every_retained_publish_carries_the_expiry(
        self, mqtt5: Observation
    ) -> None:
        """Technique: Specification-based - state, availability, discovery, meta."""
        retained = [p for p in mqtt5.broker.publishes if p.retain]

        assert self.state_topic in {p.topic for p in retained}
        assert any(p.topic.startswith("homeassistant/") for p in retained)
        assert {p.expiry for p in retained} == {EXPIRY_SECONDS}

    def test_non_retained_publishes_carry_no_expiry(self, mqtt5: Observation) -> None:
        """Technique: Equivalence Partitioning - only retained messages expire."""
        assert {p.expiry for p in mqtt5.broker.publishes if not p.retain} <= {None}

    def test_each_retained_topic_is_refreshed_once_per_window(
        self, mqtt5: Observation
    ) -> None:
        """Technique: State Transition - the duplicate-refresh cost is one per window.

        A consumer of the state topic sees the last payload again every
        ``expiry / 3`` (8 h by default). Consumers that compare values are
        unaffected; consumers that react to message receipt see a duplicate.
        """
        for window, counts in enumerate(mqtt5.window_counts, start=1):
            assert counts == {
                topic: count + window for topic, count in mqtt5.startup_counts.items()
            }

    def test_refresh_replays_the_last_state_payload(self, mqtt5: Observation) -> None:
        """Technique: Error Guessing - a refresh is byte-identical, not a new read."""
        publishes = mqtt5.broker.publishes_to(self.state_topic)

        assert len(publishes) == mqtt5.startup_counts[self.state_topic] + WINDOWS
        assert len({p.payload for p in publishes}) == 1

    def test_no_retained_topic_expires_while_the_app_runs(
        self, mqtt5: Observation
    ) -> None:
        """Technique: State Transition - the ledger outlives several expiry spans."""
        assert mqtt5.window_expired == [[]] * WINDOWS


class Mqtt311Contract:
    """The default stays MQTT 3.1.1: no expiry property, no refresh traffic."""

    def test_connects_without_a_protocol_override(self, mqtt311: Observation) -> None:
        """Technique: Equivalence Partitioning - 3.1.1 leaves aiomqtt's default."""
        assert "protocol" not in mqtt311.broker.connects[0]

    def test_retained_publishes_carry_no_expiry(self, mqtt311: Observation) -> None:
        """Technique: Specification-based - the 3.1.1 wire stays unchanged."""
        assert {p.expiry for p in mqtt311.broker.publishes} == {None}

    def test_retained_topics_are_never_republished(self, mqtt311: Observation) -> None:
        """Technique: State Transition - no refresh loop runs under 3.1.1."""
        assert mqtt311.window_counts == [mqtt311.startup_counts] * WINDOWS
