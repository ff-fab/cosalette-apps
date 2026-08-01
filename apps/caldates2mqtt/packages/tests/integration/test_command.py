"""Integration tests for re-read command dispatch in caldates2mqtt.

Exercises the full command path: MQTT inbound -> TopicRouter -> device
command handler -> FakeCalDavReader.read_events -> MQTT state publish,
using the real application wiring with in-memory test doubles.

Test Techniques Used:
- Integration Testing: Full command dispatch through cosalette framework
- Specification-based: Command payload parsing (empty, JSON overrides, invalid)
- Error Guessing: Invalid JSON payload falls back to defaults
"""

from __future__ import annotations

import asyncio

import pytest
from cosalette.testing import AppHarness

from caldates2mqtt.adapters.fake import FakeCalDavReader

from .conftest import TOPIC_PREFIX

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_publish_count(harness: AppHarness, device_key: str) -> int:
    """Return the number of state messages published for *device_key*.

    Uses ``get_messages_for`` internally; kept in this helper so test
    bodies remain free of raw MQTT scanning.
    """
    return len(harness.mqtt.get_messages_for(f"{TOPIC_PREFIX}/{device_key}/state"))


async def _run_with_command(
    harness: AppHarness,
    command_topic: str,
    command_payload: dict | str,
    *,
    startup_wait: float = 0.3,
    post_command_wait: float = 0.2,
) -> None:
    """Start the harness, deliver a command, then shut down cleanly.

    Args:
        harness: Pre-built AppHarness wrapping the integration app.
        command_topic: MQTT topic to deliver the command on.
        command_payload: Command payload dict (or raw string for error-path tests).
        startup_wait: Seconds to wait after startup before delivering.
        post_command_wait: Seconds to wait after command before shutdown.
    """
    task = asyncio.create_task(harness.run())
    try:
        await asyncio.sleep(startup_wait)
        await harness.inject_command(None, command_payload, topic=command_topic)
        await asyncio.sleep(post_command_wait)
        harness.shutdown_event.set()
        await task
    finally:
        harness.shutdown_event.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Command dispatch tests
# ---------------------------------------------------------------------------


class TestReReadCommand:
    """Verify re-read command triggers a fresh CalDAV read and publishes state."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_empty_payload_triggers_reread_with_defaults(
        self,
        harness: AppHarness,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Empty payload command triggers re-read using configured defaults.

        Technique: Integration — verify command wiring through full stack.
        """
        # Act — send empty command after initial poll has published
        await _run_with_command(
            harness,
            f"{TOPIC_PREFIX}/garbage/set",
            {},
        )

        # Assert — state was published (at least initial poll + command re-read)
        assert _state_publish_count(harness, "garbage") >= 2, (
            "Expected at least 2 state publishes (initial + command); "
            f"got {_state_publish_count(harness, 'garbage')} on "
            f"{TOPIC_PREFIX}/garbage/state"
        )

        # Assert — re-read used configured days (14)
        assert fake_reader.calls[-1][4] == 14  # [4] = days

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_json_overrides_applied_to_reread(
        self,
        harness: AppHarness,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """JSON payload with entries and days overrides the re-read parameters.

        Technique: Specification-based — command payload contract.
        """
        # Act
        await _run_with_command(
            harness,
            f"{TOPIC_PREFIX}/garbage/set",
            {"entries": 1, "days": 7},
        )

        # Assert — at least one read used the overridden days=7
        days_used = [call[4] for call in fake_reader.calls]  # [4] = days
        assert 7 in days_used, (
            f"Expected at least one read with days=7; got days: {days_used}"
        )

        # Assert — state was published multiple times (initial + command)
        assert _state_publish_count(harness, "garbage") >= 2, (
            f"Expected at least 2 state publishes; "
            f"got {_state_publish_count(harness, 'garbage')}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_invalid_json_falls_back_to_defaults(
        self,
        harness: AppHarness,
        fake_reader: FakeCalDavReader,
    ) -> None:
        """Invalid JSON command payload falls back to configured defaults.

        Technique: Error Guessing — malformed payload does not crash device.
        """
        # Act — deliver raw invalid-JSON string to test the framework's
        # parse-error path; inject_command accepts str for this use case
        await _run_with_command(
            harness,
            f"{TOPIC_PREFIX}/garbage/set",
            "not-valid-json",
        )

        # Assert — state was still published (command used defaults)
        assert _state_publish_count(harness, "garbage") >= 2, (
            f"Expected at least 2 state publishes; "
            f"got {_state_publish_count(harness, 'garbage')}"
        )

        # Assert — fallback to configured days (14)
        assert fake_reader.calls[-1][4] == 14  # [4] = days
