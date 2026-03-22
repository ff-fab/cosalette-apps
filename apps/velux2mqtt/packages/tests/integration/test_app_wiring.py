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

import json

import pytest
from cosalette import App, MockMqttClient

from velux2mqtt.adapters.fake import FakeGpio
from velux2mqtt.settings import Velux2MqttSettings

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
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Velux2MqttSettings,
    ) -> None:
        """Health status topic contains an 'online' payload after startup.

        Technique: Integration — verify cosalette health reporter fires.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        assert messages, f"Expected at least one message on {TOPIC_PREFIX}/status"
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("online" in p or "available" in p for p in payloads), (
            f"No 'online'/'available' payload found; got: {payloads}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_offline_published_on_shutdown(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Velux2MqttSettings,
    ) -> None:
        """Health status contains 'offline' payload after clean shutdown.

        Technique: State Transition — startup -> shutdown lifecycle.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert
        messages = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/status")
        payloads = [payload for payload, _retain, _qos in messages]
        assert any("offline" in p or "unavailable" in p for p in payloads), (
            f"No 'offline'/'unavailable' payload found; got: {payloads}"
        )


class TestStartupHoming:
    """Verify that homing executes for both covers on startup."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_homing_presses_gpio_for_both_covers(
        self,
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Homing direction=close presses down+stop for both covers.

        Technique: Integration — verify GPIO interaction across 2 covers.
        Each cover should press its own down pin then stop pin.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

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
        integration_app: App,
        mock_mqtt: MockMqttClient,
        test_settings: Velux2MqttSettings,
    ) -> None:
        """Both covers publish position=0 after homing close.

        Technique: Specification-based — verify MQTT state after homing.
        """
        # Act
        await run_app_briefly(integration_app, mock_mqtt, test_settings)

        # Assert — both covers published position state
        blind_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/blind/state")
        window_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/window/state")
        assert blind_states, "Blind should publish state after homing"
        assert window_states, "Window should publish state after homing"

        # Position should be 0 (homed to close)
        blind_payload = json.loads(blind_states[0][0])
        window_payload = json.loads(window_states[0][0])
        assert blind_payload["position"] == 0, (
            f"Blind position should be 0 after homing close, got: {blind_payload}"
        )
        assert window_payload["position"] == 0, (
            f"Window position should be 0 after homing close, got: {window_payload}"
        )


# ---------------------------------------------------------------------------
# Command routing and GPIO isolation
# ---------------------------------------------------------------------------


class TestCommandRouting:
    """Verify that commands are routed to the correct cover."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_open_command_to_blind_presses_blind_pins(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Open command to blind triggers blind's up pin, not window's.

        Technique: Specification-based — verify per-cover GPIO pin routing.
        """
        # Act
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
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
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Open command to window triggers window's up pin, not blind's.

        Technique: Specification-based — verify per-cover GPIO isolation.
        """
        # Act
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
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
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Stop command presses stop pin and publishes position state.

        Technique: State Transition — stop command -> position published.
        """
        # Act
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            [(f"{TOPIC_PREFIX}/blind/set", "stop")],
        )

        # Assert — blind stop pin pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_stop in pressed_pins, (
            f"Blind stop pin {BLIND_CFG.pin_stop} not in pressed pins: {pressed_pins}"
        )

        # Position state published
        blind_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/blind/state")
        assert blind_states, "Blind should publish position state after stop command"


class TestGpioIsolation:
    """Verify that GPIO interactions are isolated between covers."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_sequential_commands_to_different_covers_use_correct_pins(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Commands to different covers use their respective GPIO pins.

        Technique: Integration — verify GPIO isolation under sequential commands.
        Both covers start at position 0, so both receive "open" (upward).
        """
        # Act — send open commands to both covers
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
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
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Each cover publishes to its own state topic independently.

        Technique: Specification-based — per-cover MQTT topic isolation.
        """
        # Act — send open commands to both covers (both start at 0)
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            [
                (f"{TOPIC_PREFIX}/blind/set", "open"),
                (f"{TOPIC_PREFIX}/window/set", "open"),
            ],
        )

        # Assert — each cover has its own state topic
        blind_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/blind/state")
        window_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/window/state")
        assert blind_states, "Blind should publish state"
        assert window_states, "Window should publish state"

        # Verify payloads contain position (format check)
        blind_payload = json.loads(blind_states[-1][0])
        window_payload = json.loads(window_states[-1][0])
        assert "position" in blind_payload
        assert "position" in window_payload


# ---------------------------------------------------------------------------
# MQTT subscriptions
# ---------------------------------------------------------------------------


class TestMqttSubscriptions:
    """Verify that MQTT subscriptions are active for both covers."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_both_covers_subscribe_to_set_topics(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Both covers have active MQTT subscriptions for their /set topics.

        Technique: Specification-based — verify cosalette wiring subscribes
        to the correct topics for command dispatch.
        """
        # Act
        await run_app_briefly(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
        )

        # Assert — check subscriptions contain both cover set topics
        subscribed = set(mock_mqtt.subscriptions)
        assert f"{TOPIC_PREFIX}/blind/set" in subscribed, (
            f"Blind set topic not subscribed; got: {subscribed}"
        )
        assert f"{TOPIC_PREFIX}/window/set" in subscribed, (
            f"Window set topic not subscribed; got: {subscribed}"
        )


# ---------------------------------------------------------------------------
# Invalid / unknown commands
# ---------------------------------------------------------------------------


class TestInvalidCommands:
    """Verify that invalid commands are handled gracefully at integration level."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_invalid_command_does_not_crash_or_change_state(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Unknown command payload is silently dropped — no crash, no GPIO, no new state.

        Technique: Error Guessing — malformed payload through full app wiring.
        """
        # Act — send an invalid command to blind
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            [(f"{TOPIC_PREFIX}/blind/set", "wiggle")],
        )

        # Assert — no GPIO presses occurred (no homing, no valid command)
        assert fake_gpio.presses == [], (
            f"No GPIO presses expected for invalid command; got: {fake_gpio.presses}"
        )

        # Assert — state count unchanged (only the initial publish, no extra)
        blind_states = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/blind/state")
        assert len(blind_states) == 1, (
            f"Only initial state publish expected, no extra from invalid command; "
            f"got {len(blind_states)}: {blind_states}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_valid_command_after_invalid_still_works(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """A valid command succeeds even after a prior invalid command.

        Technique: Error Guessing — verify invalid command does not poison state.
        """
        # Act — invalid then valid
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
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
