"""Integration test fixtures for wallpanel-control.

Provides a fully-wired App backed by in-memory test doubles
(FakeWallpanel, FakeWol, MockMqttClient) for end-to-end command
dispatch tests without real SSH or network I/O.
"""

from __future__ import annotations

import asyncio

import cosalette
import pytest
from cosalette import MockMqttClient
from cosalette.testing import AppHarness, FakeClock

from tests.fixtures.async_utils import wait_for_condition
from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.devices import display, system
from wallpanel_control.ports import WallpanelPort, WolPort
from wallpanel_control.settings import WallpanelControlSettings

TOPIC_PREFIX = "wallpanel-control"
DISPLAY_SET = f"{TOPIC_PREFIX}/display/set"
DISPLAY_STATE = f"{TOPIC_PREFIX}/display/state"
SYSTEM_ACTION_SET = f"{TOPIC_PREFIX}/system/action/set"
SYSTEM_ACTION_STATE = f"{TOPIC_PREFIX}/system/action/state"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_topic_for(command_topic: str) -> str:
    """Map a command topic to its corresponding state topic.

    ``<prefix>/<name>/set`` → ``<prefix>/<name>/state``.
    Works for both ``display/set`` and ``system/action/set``.
    """
    if not command_topic.endswith("/set"):
        msg = f"Expected /set suffix, got {command_topic!r}"
        raise ValueError(msg)
    return command_topic.removesuffix("/set") + "/state"


def build_integration_app(
    fake_wallpanel: FakeWallpanel,
    fake_wol: FakeWol,
) -> cosalette.App:
    """Construct a fully-wired App backed by in-memory test doubles.

    Mirrors ``wallpanel_control.main`` but replaces production adapters
    with fakes so tests run without SSH or WoL network access.
    Heartbeat and health-check timers are disabled so command tests are
    not affected by background publishes.
    """
    app = cosalette.App(
        name="wallpanel-control",
        version="0.0.0",
        settings_class=WallpanelControlSettings,
        heartbeat_interval=None,
        health_check_interval=None,
        adapters={
            WallpanelPort: lambda: fake_wallpanel,
            WolPort: lambda: fake_wol,
        },
    )
    app.include_router(display.router)
    app.include_router(system.router)
    return app


async def wait_for_subscriptions(harness: AppHarness) -> None:
    """Wait until both command routers have registered their subscriptions.

    Use this when a test needs to verify subscription state without
    delivering any commands.  ``run_with_commands`` handles subscription
    readiness automatically when delivering commands.
    """
    await wait_for_condition(
        lambda: (
            DISPLAY_SET in harness.mqtt.subscriptions
            and SYSTEM_ACTION_SET in harness.mqtt.subscriptions
        ),
        timeout=2.0,
        description="command subscriptions registered",
    )


async def run_with_commands(
    harness: AppHarness,
    commands: list[tuple[str, str]],
) -> None:
    """Start harness, deliver commands sequentially, then shut down.

    Waits until all command topics in ``commands`` are subscribed before
    the first delivery.  After each delivery, waits for at least one new
    publish before moving to the next command.  Always cleans up in a
    ``finally`` block so tests stay isolated.

    Args:
        harness: Pre-built AppHarness wrapping the integration app.
        commands: Ordered ``(topic, payload)`` pairs to deliver.
            Must not be empty; use ``wait_for_subscriptions`` for
            subscription-only checks.

    Raises:
        ValueError: If ``commands`` is empty.
    """
    if not commands:
        raise ValueError(
            "commands must not be empty; use wait_for_subscriptions for subscription-only checks"
        )
    expected_subs: frozenset[str] = frozenset(t for t, _ in commands)
    task = asyncio.create_task(harness.run())
    try:
        await wait_for_condition(
            lambda: expected_subs.issubset(harness.mqtt.subscriptions),
            timeout=2.0,
            description="command subscriptions registered",
        )
        for topic, payload in commands:
            state_topic = _state_topic_for(topic)
            before = len(harness.mqtt.get_messages_for(state_topic))
            await harness.mqtt.deliver(topic, payload)
            await wait_for_condition(
                lambda st=state_topic, n=before: (
                    len(harness.mqtt.get_messages_for(st)) > n
                ),
                timeout=2.0,
                description=f"state publish on {state_topic} after command to {topic}",
            )
    finally:
        harness.shutdown_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def harness(fake_wallpanel: FakeWallpanel, fake_wol: FakeWol) -> AppHarness:
    """Fresh AppHarness wired with FakeWallpanel and FakeWol."""
    return AppHarness(
        app=build_integration_app(fake_wallpanel, fake_wol),
        mqtt=MockMqttClient(),
        clock=FakeClock(),
        settings=make_wallpanel_control_settings(),
        shutdown_event=asyncio.Event(),
    )
