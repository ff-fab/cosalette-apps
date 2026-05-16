"""Integration tests for wallpanel-control full MQTT command path.

Exercises the complete path from MQTT inbound command → cosalette
command router → handler → FakeWallpanel / FakeWol side-effects →
MQTT state publish, using in-memory test doubles with no real SSH
or network I/O.

Test Techniques Used:
- Integration Testing: Full app wiring through cosalette framework
  (App → Router → command handler → adapter → MQTT state publish)
- Specification-based Testing: Topic layout matches main.py docstring
  (display/set → display/state, system/action/set → system/action/state)
- State Transition Testing: unreachable → reachable produces
  unavailable then available state publishes
- Equivalence Partitioning: display command with state+brightness,
  system wake (WoL) vs hibernate (SSH) as distinct partitions
- Error Guessing: command while wallpanel unreachable returns
  available=false without crashing the app
"""

from __future__ import annotations

import asyncio
import json

import pytest
from cosalette.testing import AppHarness

from tests.fixtures.async_utils import wait_for_condition
from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol

from .conftest import (
    DISPLAY_SET,
    DISPLAY_STATE,
    SYSTEM_ACTION_SET,
    SYSTEM_ACTION_STATE,
    run_with_commands,
)

# ---------------------------------------------------------------------------
# TestSubscriptions
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSubscriptions:
    """Verify that the app registers command topic subscriptions on startup.

    Technique: Specification-based — topic layout from main.py docstring.
    """

    async def test_subscribes_to_display_and_system_action_topics(
        self, harness: AppHarness
    ) -> None:
        """Both command topics are subscribed before the first command.

        Arrange: fresh harness with FakeWallpanel and FakeWol.
        Act: start the app and wait for subscriptions.
        Assert: display/set and system/action/set appear in mqtt.subscriptions.
        """
        task = asyncio.create_task(harness.run())
        try:
            await wait_for_condition(
                lambda: (
                    DISPLAY_SET in harness.mqtt.subscriptions
                    and SYSTEM_ACTION_SET in harness.mqtt.subscriptions
                ),
                timeout=2.0,
                description="command subscriptions registered",
            )
        finally:
            harness.shutdown_event.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        assert DISPLAY_SET in harness.mqtt.subscriptions
        assert SYSTEM_ACTION_SET in harness.mqtt.subscriptions


# ---------------------------------------------------------------------------
# TestDisplayCommand
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDisplayCommand:
    """End-to-end display command dispatch tests.

    Technique: Integration — verify adapter side-effects and state publish.
    """

    async def test_state_on_with_brightness_updates_wallpanel_and_publishes_state(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Display command state=on+brightness_percent=60 updates FakeWallpanel.

        Arrange: FakeWallpanel with screen off (screen_state=False) to exercise
            the screen off → on transition path.
        Act: deliver {"state": "on", "brightness_percent": 60}.
        Assert:
          - FakeWallpanel.screen_state is True
          - FakeWallpanel.brightness ≈ round(7812 * 60 / 100) = 4687
          - Published display state has available=true, state="on",
            brightness_percent=60

        Technique: State Transition — screen off → on with brightness applied.
        """
        fake_wallpanel.screen_state = False
        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"state": "on", "brightness_percent": 60}')],
        )

        assert fake_wallpanel.screen_state is True
        assert fake_wallpanel.brightness == 4687

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is True
        assert payload["state"] == "on"
        assert payload["brightness_percent"] == 60

    async def test_display_command_while_unreachable_publishes_unavailable_state(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Display command while unreachable publishes available=false.

        Arrange: FakeWallpanel marked unreachable before any command.
        Act: deliver {"state": "on", "brightness_percent": 60}.
        Assert: published state has available=false, null state and brightness.

        Technique: Equivalence Partitioning — unreachable as distinct input
        partition from the happy path.
        """
        fake_wallpanel.set_reachable(False)

        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"state": "on", "brightness_percent": 60}')],
        )

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is False
        assert payload["state"] is None
        assert payload["brightness_percent"] is None

    async def test_display_state_off_turns_screen_off_and_publishes_state(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Display command state=off turns screen off and publishes available state.

        Arrange: FakeWallpanel with screen on (default screen_state=True).
        Act: deliver {"state": "off"}.
        Assert:
          - FakeWallpanel.screen_state is False
          - Published display state has available=true, state="off"

        Technique: Equivalence Partitioning — off as a distinct valid input partition.
        """
        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"state": "off"}')],
        )

        assert fake_wallpanel.screen_state is False

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is True
        assert payload["state"] == "off"
        assert payload["brightness_percent"] is not None

    async def test_state_on_only_reads_current_brightness_without_setting_it(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """State=on command without brightness reads current brightness, does not set it.

        Arrange: FakeWallpanel with screen off (screen_state=False), brightness=4000.
        Act: deliver {"state": "on"} (no brightness_percent field).
        Assert:
          - FakeWallpanel.screen_state is True (screen turned on)
          - FakeWallpanel.brightness unchanged at 4000 (no set_brightness call)
          - Published display state has available=true, state="on",
            brightness_percent=51 (round(4000/7812*100))

        Technique: Equivalence Partitioning — state=on without brightness as a
        distinct branch from state=on+brightness (read vs write path).
        """
        fake_wallpanel.screen_state = False
        fake_wallpanel.brightness = 4000

        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"state": "on"}')],
        )

        assert fake_wallpanel.screen_state is True
        assert fake_wallpanel.brightness == 4000  # unchanged

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is True
        assert payload["state"] == "on"
        assert payload["brightness_percent"] == 51  # round(4000/7812*100)

    async def test_brightness_only_command_sets_brightness_without_state_change(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Brightness-only command sets brightness without turning screen on.

        Arrange: FakeWallpanel with screen already on (default screen_state=True).
        Act: deliver {"brightness_percent": 75} (no state field).
        Assert:
          - FakeWallpanel.brightness \u2248 round(7812 * 75 / 100) = 5859
          - Published display state has available=true, state="on", brightness_percent=75          - FakeWallpanel.screen_state remains True (no redundant screen toggle)
        Technique: Equivalence Partitioning — brightness-only as third valid command variant.
        """
        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"brightness_percent": 75}')],
        )

        assert fake_wallpanel.brightness == 5859

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is True
        assert payload["state"] == "on"
        assert payload["brightness_percent"] == 75

        assert fake_wallpanel.screen_state is True

    async def test_brightness_only_command_with_screen_off_turns_screen_on(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Brightness-only command with screen off auto-turns screen on.

        Arrange: FakeWallpanel with screen off (screen_state=False).
        Act: deliver {"brightness_percent": 50} (no state field).
        Assert:
          - FakeWallpanel.screen_state is True (auto screen-on triggered)
          - FakeWallpanel.brightness ≈ round(7812 * 50 / 100) = 3906
          - Published display state has available=true, state="on", brightness_percent=50

        Technique: State Transition — screen off → on triggered implicitly by
        brightness-only command (distinct from explicit state=on command).
        """
        fake_wallpanel.screen_state = False

        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"brightness_percent": 50}')],
        )

        assert fake_wallpanel.screen_state is True
        assert fake_wallpanel.brightness == 3906

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is True
        assert payload["state"] == "on"
        assert payload["brightness_percent"] == 50

    async def test_brightness_only_command_while_unreachable_publishes_unavailable(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Brightness-only command while unreachable publishes available=false.

        Arrange: FakeWallpanel marked unreachable.
        Act: deliver {"brightness_percent": 75}.
        Assert: published state has available=false, null state and brightness.

        Technique: Equivalence Partitioning — brightness-only unreachable sub-path
        (distinct from state+brightness unreachable path).
        """
        fake_wallpanel.set_reachable(False)

        await run_with_commands(
            harness,
            [(DISPLAY_SET, '{"brightness_percent": 75}')],
        )

        messages = harness.mqtt.get_messages_for(DISPLAY_STATE)
        assert messages, f"No publish on {DISPLAY_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["available"] is False
        assert payload["state"] is None
        assert payload["brightness_percent"] is None

    async def test_display_unreachable_then_reachable_transitions_state(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Wallpanel transitions unreachable→reachable: unavailable then available.

        Arrange: FakeWallpanel starts unreachable.
        Act (1): deliver display command → expect available=false publish.
        Arrange: mark wallpanel reachable.
        Act (2): deliver same command → expect available=true publish.

        Technique: State Transition — two-step transition across reachability
        boundary within a single app run.
        """
        fake_wallpanel.set_reachable(False)

        task = asyncio.create_task(harness.run())
        try:
            await wait_for_condition(
                lambda: DISPLAY_SET in harness.mqtt.subscriptions,
                timeout=2.0,
                description="display/set subscribed",
            )

            # First command — unreachable
            before1 = len(harness.mqtt.get_messages_for(DISPLAY_STATE))
            await harness.mqtt.deliver(
                DISPLAY_SET, '{"state": "on", "brightness_percent": 60}'
            )
            await wait_for_condition(
                lambda: len(harness.mqtt.get_messages_for(DISPLAY_STATE)) > before1,
                timeout=2.0,
                description="unavailable state published",
            )

            msgs = harness.mqtt.get_messages_for(DISPLAY_STATE)
            payload1 = json.loads(msgs[-1][0])
            assert payload1["available"] is False

            # Transition to reachable
            fake_wallpanel.set_reachable(True)

            # Second command — now reachable
            before2 = len(harness.mqtt.get_messages_for(DISPLAY_STATE))
            await harness.mqtt.deliver(
                DISPLAY_SET, '{"state": "on", "brightness_percent": 60}'
            )
            await wait_for_condition(
                lambda: len(harness.mqtt.get_messages_for(DISPLAY_STATE)) > before2,
                timeout=2.0,
                description="available state published",
            )

            msgs = harness.mqtt.get_messages_for(DISPLAY_STATE)
            payload2 = json.loads(msgs[-1][0])
            assert payload2["available"] is True
            assert payload2["state"] == "on"
            assert payload2["brightness_percent"] == 60

        finally:
            harness.shutdown_event.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


# ---------------------------------------------------------------------------
# TestSystemAction
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSystemAction:
    """End-to-end system action command dispatch tests.

    Technique: Integration — verify adapter calls and state publish.
    """

    async def test_hibernate_action_calls_fake_wallpanel_and_publishes_accepted(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Hibernate action calls wallpanel.hibernate() and publishes accepted=true.

        Arrange: reachable FakeWallpanel.
        Act: deliver {"action": "hibernate"}.
        Assert:
          - FakeWallpanel.power_state == "hibernating"
          - FakeWallpanel.reachable is False (hibernate side-effect)
          - Published state has accepted=true, action="hibernate"

        Technique: State Transition — running → hibernating.
        """
        await run_with_commands(
            harness,
            [(SYSTEM_ACTION_SET, '{"action": "hibernate"}')],
        )

        assert fake_wallpanel.power_state == "hibernating"
        assert fake_wallpanel.reachable is False

        messages = harness.mqtt.get_messages_for(SYSTEM_ACTION_STATE)
        assert messages, f"No publish on {SYSTEM_ACTION_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["accepted"] is True
        assert payload["action"] == "hibernate"

    async def test_wake_action_calls_fake_wol_and_publishes_accepted(
        self,
        harness: AppHarness,
        fake_wol: FakeWol,
    ) -> None:
        """Wake action calls wol.wake() with configured MAC and publishes accepted=true.

        Arrange: fresh FakeWol with no prior calls.
        Act: deliver {"action": "wake"}.
        Assert:
          - FakeWol.calls contains one entry with the configured MAC
          - Published state has accepted=true, action="wake"

        Technique: Specification-based — wake uses WoL, not SSH.
        """
        await run_with_commands(
            harness,
            [(SYSTEM_ACTION_SET, '{"action": "wake"}')],
        )

        assert len(fake_wol.calls) == 1
        mac, broadcast = fake_wol.calls[0]
        assert mac == "AA:BB:CC:DD:EE:FF"
        assert broadcast == "255.255.255.255"

        messages = harness.mqtt.get_messages_for(SYSTEM_ACTION_STATE)
        assert messages, f"No publish on {SYSTEM_ACTION_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["accepted"] is True
        assert payload["action"] == "wake"

    async def test_hibernate_while_unreachable_publishes_accepted_false(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Hibernate while unreachable publishes accepted=false.

        Arrange: FakeWallpanel marked unreachable (e.g., already hibernating).
        Act: deliver {"action": "hibernate"}.
        Assert: published state has accepted=false, action="hibernate".

        Technique: Error Guessing — SSH command on unreachable host.
        """
        fake_wallpanel.set_reachable(False)

        await run_with_commands(
            harness,
            [(SYSTEM_ACTION_SET, '{"action": "hibernate"}')],
        )

        messages = harness.mqtt.get_messages_for(SYSTEM_ACTION_STATE)
        assert messages, f"No publish on {SYSTEM_ACTION_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["accepted"] is False
        assert payload["action"] == "hibernate"

    async def test_suspend_action_calls_fake_wallpanel_and_publishes_accepted(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
    ) -> None:
        """Suspend action calls wallpanel.suspend() and publishes accepted=true.

        Arrange: reachable FakeWallpanel.
        Act: deliver {"action": "suspend"}.
        Assert:
          - FakeWallpanel.power_state == "suspended"
          - Published state has accepted=true, action="suspend"

        Technique: Equivalence Partitioning — suspend as a distinct action partition
        from hibernate (same SSH path, different command).
        """
        await run_with_commands(
            harness,
            [(SYSTEM_ACTION_SET, '{"action": "suspend"}')],
        )

        assert fake_wallpanel.power_state == "suspended"

        messages = harness.mqtt.get_messages_for(SYSTEM_ACTION_STATE)
        assert messages, f"No publish on {SYSTEM_ACTION_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["accepted"] is True
        assert payload["action"] == "suspend"

    async def test_wake_while_unreachable_still_publishes_accepted_true(
        self,
        harness: AppHarness,
        fake_wallpanel: FakeWallpanel,
        fake_wol: FakeWol,
    ) -> None:
        """Wake succeeds even when wallpanel SSH is unreachable (WoL bypass).

        Arrange: FakeWallpanel marked unreachable (simulating powered-off state).
        Act: deliver {"action": "wake"}.
        Assert:
          - FakeWol.calls contains one entry (WoL sent regardless of SSH state)
          - Published state has accepted=true, action="wake"

        Technique: Specification-based — pins the WoL-vs-SSH contract: wake
        never requires SSH connectivity.
        """
        fake_wallpanel.set_reachable(False)

        await run_with_commands(
            harness,
            [(SYSTEM_ACTION_SET, '{"action": "wake"}')],
        )

        assert len(fake_wol.calls) == 1

        messages = harness.mqtt.get_messages_for(SYSTEM_ACTION_STATE)
        assert messages, f"No publish on {SYSTEM_ACTION_STATE}"
        payload = json.loads(messages[-1][0])
        assert payload["accepted"] is True
        assert payload["action"] == "wake"
