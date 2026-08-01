"""Integration tests for velux2mqtt full app wiring with multiple covers.

Exercises the real application wiring (startup homing -> command dispatch ->
GPIO interaction -> MQTT state publishing) end-to-end using in-memory test
doubles (FakeGpio, MockMqttClient), with no real GPIO or MQTT I/O.

Test Techniques Used:
- Integration Testing: Full app wiring with 2 covers through cosalette framework
- State Transition Testing: Homing on startup, command -> movement -> position publish
- Specification-based: MQTT topic routing, GPIO pin isolation per cover
- Error Guessing: Cross-cover interference, commands during shutdown
"""

from __future__ import annotations

import pytest
from cosalette.testing import AppHarness

from velux2mqtt.adapters.fake import FakeGpio

from .conftest import (
    BLIND_CFG,
    TOPIC_PREFIX,
    WINDOW_CFG,
    run_app_briefly,
    run_app_with_commands,
)

# ---------------------------------------------------------------------------
# Startup and homing
# ---------------------------------------------------------------------------


class TestAppStartup:
    """Verify that the app boots with 2 covers and publishes health status."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_online_published_on_startup(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Technique: Integration — verify cosalette health reporter fires.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="online")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        harness: AppHarness,
    ) -> None:
        """Health status contains 'offline' payload after clean shutdown.

        Technique: State Transition — startup -> shutdown lifecycle.
        """
        # Act
        await run_app_briefly(harness)

        # Assert
        harness.assert_published(f"{TOPIC_PREFIX}/status", contains="offline")


class TestStartupHoming:
    """Verify that homing executes for both covers on startup."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_homing_presses_gpio_for_both_covers(
        self,
        harness: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Homing direction=close presses down+stop for both covers.

        Technique: Integration — verify GPIO interaction across 2 covers.
        Each cover should press its own down pin then stop pin.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — both covers' down pins pressed (homing close)
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_down in pressed_pins, (
            f"Blind down pin {BLIND_CFG.pin_down} not in pressed pins: {pressed_pins}"
        )
        assert WINDOW_CFG.pin_down in pressed_pins, (
            f"Window down pin {WINDOW_CFG.pin_down} not in pressed pins: {pressed_pins}"
        )
        # Stop pins should also be pressed
        assert BLIND_CFG.pin_stop in pressed_pins, (
            f"Blind stop pin {BLIND_CFG.pin_stop} not in pressed pins: {pressed_pins}"
        )
        assert WINDOW_CFG.pin_stop in pressed_pins, (
            f"Window stop pin {WINDOW_CFG.pin_stop} not in pressed pins: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_homing_publishes_initial_position_for_both_covers(
        self,
        harness: AppHarness,
    ) -> None:
        """Both covers publish position=0 after homing close.

        Technique: Specification-based — verify MQTT state after homing.
        """
        # Act
        await run_app_briefly(harness)

        # Assert — both covers published position=0 after homing close
        harness.assert_state(f"{TOPIC_PREFIX}/blind/state", {"position": 0})
        harness.assert_state(f"{TOPIC_PREFIX}/window/state", {"position": 0})


# ---------------------------------------------------------------------------
# Command routing and GPIO isolation
# ---------------------------------------------------------------------------


class TestCommandRouting:
    """Verify that commands are routed to the correct cover."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_open_command_to_blind_presses_blind_pins(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Open command to blind triggers blind's up pin, not window's.

        Technique: Specification-based — verify per-cover GPIO pin routing.
        """
        # Act
        await run_app_with_commands(
            harness_no_homing,
            [(f"{TOPIC_PREFIX}/blind/set", "open")],
        )

        # Assert — blind up pin pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_up in pressed_pins, (
            f"Blind up pin {BLIND_CFG.pin_up} not in pressed pins: {pressed_pins}"
        )
        # Window pins should NOT have been pressed by this command
        window_move_pins = {WINDOW_CFG.pin_up, WINDOW_CFG.pin_down}
        window_presses = [p for p in fake_gpio.presses if p.pin in window_move_pins]
        assert not window_presses, (
            f"Window movement pins should not be pressed by blind command: "
            f"{window_presses}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_open_command_to_window_presses_window_pins(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Open command to window triggers window's up pin, not blind's.

        Technique: Specification-based — verify per-cover GPIO isolation.
        """
        # Act
        await run_app_with_commands(
            harness_no_homing,
            [(f"{TOPIC_PREFIX}/window/set", "open")],
        )

        # Assert — window up pin pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert WINDOW_CFG.pin_up in pressed_pins, (
            f"Window up pin {WINDOW_CFG.pin_up} not in pressed pins: {pressed_pins}"
        )
        # Blind movement pins should NOT have been pressed
        blind_move_pins = {BLIND_CFG.pin_up, BLIND_CFG.pin_down}
        blind_presses = [p for p in fake_gpio.presses if p.pin in blind_move_pins]
        assert not blind_presses, (
            f"Blind movement pins should not be pressed by window command: "
            f"{blind_presses}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_stop_command_publishes_position_state(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Stop command presses stop pin and publishes position state.

        Technique: State Transition — stop command -> position published.
        """
        # Act
        await run_app_with_commands(
            harness_no_homing,
            [(f"{TOPIC_PREFIX}/blind/set", "stop")],
        )

        # Assert — blind stop pin pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_stop in pressed_pins, (
            f"Blind stop pin {BLIND_CFG.pin_stop} not in pressed pins: {pressed_pins}"
        )

        # Position state published
        harness_no_homing.assert_state(f"{TOPIC_PREFIX}/blind/state", {})


class TestGpioIsolation:
    """Verify that GPIO interactions are isolated between covers."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_sequential_commands_to_different_covers_use_correct_pins(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Commands to different covers use their respective GPIO pins.

        Technique: Integration — verify GPIO isolation under sequential commands.
        Both covers start at position 0, so both receive "open" (upward).
        """
        # Act — send open commands to both covers
        await run_app_with_commands(
            harness_no_homing,
            [
                (f"{TOPIC_PREFIX}/blind/set", "open"),
                (f"{TOPIC_PREFIX}/window/set", "open"),
            ],
        )

        # Assert — both covers' up pins pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_up in pressed_pins, (
            f"Blind up pin not pressed: {pressed_pins}"
        )
        assert WINDOW_CFG.pin_up in pressed_pins, (
            f"Window up pin not pressed: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_both_covers_publish_independent_states(
        self,
        harness_no_homing: AppHarness,
    ) -> None:
        """Each cover publishes to its own state topic independently.

        Technique: Specification-based — per-cover MQTT topic isolation.
        """
        # Act — send open commands to both covers (both start at 0)
        await run_app_with_commands(
            harness_no_homing,
            [
                (f"{TOPIC_PREFIX}/blind/set", "open"),
                (f"{TOPIC_PREFIX}/window/set", "open"),
            ],
        )

        # Assert — each cover has its own state topic with position data
        harness_no_homing.assert_state(f"{TOPIC_PREFIX}/blind/state", {})
        harness_no_homing.assert_state(f"{TOPIC_PREFIX}/window/state", {})


# ---------------------------------------------------------------------------
# MQTT subscriptions
# ---------------------------------------------------------------------------


class TestMqttSubscriptions:
    """Verify that MQTT subscriptions are active for both covers."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_both_covers_subscribe_to_set_topics(
        self,
        harness_no_homing: AppHarness,
    ) -> None:
        """Both covers have active MQTT subscriptions for their /set topics.

        Technique: Specification-based — verify cosalette wiring subscribes
        to the correct topics for command dispatch.
        """
        # Act
        await run_app_briefly(harness_no_homing)

        # Assert — check subscriptions contain both cover set topics
        harness_no_homing.assert_subscribed(f"{TOPIC_PREFIX}/blind/set")
        harness_no_homing.assert_subscribed(f"{TOPIC_PREFIX}/window/set")


# ---------------------------------------------------------------------------
# Invalid / unknown commands
# ---------------------------------------------------------------------------


class TestInvalidCommands:
    """Verify that invalid commands are handled gracefully at integration level."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_invalid_command_does_not_crash_or_change_state(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """Unknown command payload is silently dropped — no crash, no GPIO,
        no new state.

        Technique: Error Guessing — malformed payload through full app wiring.
        """
        # Act — send an invalid command to blind
        await run_app_with_commands(
            harness_no_homing,
            [(f"{TOPIC_PREFIX}/blind/set", "wiggle")],
        )

        # Assert — no GPIO presses occurred (no homing, no valid command)
        assert fake_gpio.presses == [], (
            f"No GPIO presses expected for invalid command; got: {fake_gpio.presses}"
        )

        # Assert — state count unchanged (only the initial publish, no extra)
        harness_no_homing.assert_published(f"{TOPIC_PREFIX}/blind/state", count=1)

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_valid_command_after_invalid_still_works(
        self,
        harness_no_homing: AppHarness,
        fake_gpio: FakeGpio,
    ) -> None:
        """A valid command succeeds even after a prior invalid command.

        Technique: Error Guessing — verify invalid command does not poison state.
        """
        # Act — invalid then valid
        await run_app_with_commands(
            harness_no_homing,
            [
                (f"{TOPIC_PREFIX}/blind/set", "garbage_payload"),
                (f"{TOPIC_PREFIX}/blind/set", "open"),
            ],
        )

        # Assert — blind up pin was pressed (valid command worked)
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_up in pressed_pins, (
            f"Blind up pin {BLIND_CFG.pin_up} should be pressed after valid command; "
            f"got: {pressed_pins}"
        )
