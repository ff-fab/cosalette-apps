"""Unit tests for the run_app_with_commands helpers in integration/conftest.py.

Test Techniques Used:
- Equivalence Partitioning: topic shapes (root, 3-segment, 4-segment sub-topic)
- Boundary Value Analysis: exactly-at-deadline vs. resolved-before-deadline polling
- Specification-based: TopicRouter.subscriptions registers root and wildcard
  topics as two distinct strings (see cosalette._mqtt._router.TopicRouter),
  so a sub-topic command's expected subscriptions must include both.
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette.testing import AppHarness

from .conftest import _expected_subscriptions, _wait_until_subscribed


class TestExpectedSubscriptions:
    """_expected_subscriptions maps a command topic to the subscription(s) it needs."""

    def test_root_level_command_returns_itself(self) -> None:
        """A 2-segment root command ({prefix}/set) has no device segment —
        itself is the subscription.

        Technique: Equivalence Partitioning — the previously-untested boundary
        case where a topic has no device segment.
        """
        assert _expected_subscriptions("velux2mqtt/set") == {"velux2mqtt/set"}

    def test_root_device_command_returns_root_topic(self) -> None:
        """A 3-segment device command needs only its own root subscription."""
        assert _expected_subscriptions("velux2mqtt/blind/set") == {
            "velux2mqtt/blind/set"
        }

    def test_sub_topic_command_returns_root_and_wildcard(self) -> None:
        """A 4-segment sub-topic command needs both the root and wildcard
        subscriptions — TopicRouter.subscriptions registers them as two
        distinct topic strings, and the wildcard is the one the router
        actually matches sub-topic commands against.
        """
        assert _expected_subscriptions("velux2mqtt/blind/calibrate/set") == {
            "velux2mqtt/blind/set",
            "velux2mqtt/blind/+/set",
        }


class TestWaitUntilSubscribed:
    """_wait_until_subscribed polls harness.mqtt.subscriptions until *topics* appear."""

    async def test_returns_once_topics_are_already_subscribed(self) -> None:
        """Resolves immediately when the condition already holds.

        Technique: Specification-based — success path.
        """
        harness = AppHarness.create()
        harness.mqtt.subscriptions.append("velux2mqtt/blind/set")

        await _wait_until_subscribed(harness, {"velux2mqtt/blind/set"}, timeout=0.05)

    async def test_raises_with_missing_topics_when_never_subscribed(self) -> None:
        """Raises AssertionError naming the missing topics once the deadline passes.

        Technique: Boundary Value Analysis — the deadline-exceeded branch,
        otherwise untested by any integration test (they all take the
        success path).
        """
        harness = AppHarness.create()

        with pytest.raises(AssertionError, match="velux2mqtt/blind/set"):
            await _wait_until_subscribed(
                harness,
                {"velux2mqtt/blind/set"},
                timeout=0.02,
                poll_interval=0.005,
            )

    async def test_raises_with_actual_subscriptions_for_debuggability(self) -> None:
        """The timeout error reports what *was* subscribed, not just what's missing.

        Technique: Specification-based — the error message must carry enough
        context (actual vs. expected) to diagnose a naming mismatch instead
        of "subscribed to nothing at all".
        """
        harness = AppHarness.create()
        harness.mqtt.subscriptions.append("velux2mqtt/window/set")

        with pytest.raises(AssertionError, match="velux2mqtt/window/set"):
            await _wait_until_subscribed(
                harness,
                {"velux2mqtt/blind/set"},
                timeout=0.02,
                poll_interval=0.005,
            )

    async def test_resolves_once_topic_appears_mid_poll(self) -> None:
        """Picks up a subscription that appears after polling has started.

        Technique: State Transition — unsubscribed -> subscribed while waiting.
        """
        harness = AppHarness.create()

        async def subscribe_soon() -> None:
            await asyncio.sleep(0.01)
            harness.mqtt.subscriptions.append("velux2mqtt/blind/set")

        asyncio.create_task(subscribe_soon())
        await _wait_until_subscribed(
            harness, {"velux2mqtt/blind/set"}, timeout=1.0, poll_interval=0.005
        )
