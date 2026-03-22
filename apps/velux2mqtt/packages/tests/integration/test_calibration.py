"""Integration tests for velux2mqtt calibration end-to-end flow.

Exercises the full calibration MQTT ping-pong through the real app wiring:
start calibration on one cover, send go/mark commands for multiple runs in
each direction, verify status messages at each step, verify final results
published, verify normal commands rejected during calibration, and verify
the second cover is unaffected.

Test Techniques Used:
- State Transition Testing: Full calibration lifecycle IDLE -> READY -> TIMING -> COMPLETE
- Integration Testing: Full app wiring with MQTT command delivery and GPIO interaction
- Specification-based: MQTT topic payloads, calibration result format, direction alternation
- Error Guessing: Normal commands during calibration, cross-cover interference
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
    run_app_with_commands,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cal_cmd(action: str, **kwargs: object) -> str:
    """Build a calibration JSON command payload."""
    data: dict[str, object] = {"calibrate": action, **kwargs}
    return json.dumps(data)


def _get_cal_states(mock_mqtt: MockMqttClient, cover: str) -> list[dict[str, object]]:
    """Extract parsed calibration state messages for a cover."""
    raw = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/{cover}/calibrate/state")
    return [json.loads(payload) for payload, _retain, _qos in raw]


def _get_cal_results(mock_mqtt: MockMqttClient, cover: str) -> list[dict[str, object]]:
    """Extract parsed calibration result messages for a cover."""
    raw = mock_mqtt.get_messages_for(f"{TOPIC_PREFIX}/{cover}/calibrate/result")
    return [json.loads(payload) for payload, _retain, _qos in raw]


# ---------------------------------------------------------------------------
# Full calibration flow
# ---------------------------------------------------------------------------


class TestCalibrationFlow:
    """Full calibration flow end-to-end via MQTT commands."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_single_run_calibration_publishes_states_and_result(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Single-run calibration publishes correct state at each step and final result.

        Technique: State Transition Testing -- IDLE -> READY -> TIMING -> READY
        -> TIMING -> COMPLETE, verifying each published state.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # Act -- full single-run calibration sequence
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # close timing
            (blind_set, _cal_cmd("mark")),  # end close -> READY (open)
            (blind_set, _cal_cmd("go")),  # open timing
            (blind_set, _cal_cmd("mark")),  # end open -> COMPLETE
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- calibration states published in order
        states = _get_cal_states(mock_mqtt, "blind")
        assert len(states) >= 5, (
            f"Expected >= 5 state messages, got {len(states)}: {states}"
        )

        # Step 1: start -> READY, run=1, direction=CLOSE
        assert states[0]["state"] == "READY"
        assert states[0]["run"] == 1
        assert states[0]["direction"] == "CLOSE"

        # Step 2: go -> TIMING
        assert states[1]["state"] == "TIMING"

        # Step 3: mark -> READY (switches to OPEN)
        assert states[2]["state"] == "READY"
        assert states[2]["direction"] == "OPEN"

        # Step 4: go -> TIMING
        assert states[3]["state"] == "TIMING"

        # Step 5: mark -> COMPLETE
        assert states[4]["state"] == "COMPLETE"

        # Assert -- result published
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert "avg_close" in results[0]
        assert "avg_open" in results[0]
        assert isinstance(results[0]["avg_close"], float)
        assert isinstance(results[0]["avg_open"], float)

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_multi_run_calibration_completes(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Two-run calibration produces averaged result across both runs.

        Technique: Specification-based -- verify multi-run direction alternation
        and final averaged result.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # 2 runs: close/open, close/open
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=2)),
            # Run 1
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
            # Run 2
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- final state is COMPLETE
        states = _get_cal_states(mock_mqtt, "blind")
        assert states[-1]["state"] == "COMPLETE"

        # Assert -- result published with averaged values
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 1
        assert results[0]["avg_close"] > 0
        assert results[0]["avg_open"] > 0

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_calibration_go_presses_correct_gpio_pins(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Go commands press the correct GPIO pins for each direction.

        Technique: Specification-based -- CLOSE presses down pin,
        OPEN presses up pin.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # close -> down pin
            (blind_set, _cal_cmd("mark")),
            (blind_set, _cal_cmd("go")),  # open -> up pin
            (blind_set, _cal_cmd("mark")),
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- down pin (close) and up pin (open) both pressed
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_down in pressed_pins, (
            f"Down pin {BLIND_CFG.pin_down} expected for close direction; "
            f"got: {pressed_pins}"
        )
        assert BLIND_CFG.pin_up in pressed_pins, (
            f"Up pin {BLIND_CFG.pin_up} expected for open direction; "
            f"got: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_cancel_returns_to_idle(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Cancel during calibration returns state to IDLE.

        Technique: State Transition Testing -- cancel from READY -> IDLE.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("cancel")),
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- last state is IDLE
        states = _get_cal_states(mock_mqtt, "blind")
        assert states[-1]["state"] == "IDLE"

        # Assert -- no result published
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Normal command blocking during calibration
# ---------------------------------------------------------------------------


class TestCalibrationCommandBlocking:
    """Normal commands are rejected during active calibration."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_normal_command_rejected_during_ready_state(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Open command is ignored while calibration is in READY state.

        Technique: Error Guessing -- concurrent normal command during calibration.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, "open"),  # should be rejected
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- blind up pin NOT pressed by "open" command
        # (no movement pins pressed; only calibration state published)
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_up not in pressed_pins, (
            f"Up pin {BLIND_CFG.pin_up} should NOT be pressed during calibration; "
            f"got: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_normal_command_rejected_during_timing_state(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Stop command is ignored while calibration is in TIMING state.

        Technique: Error Guessing -- stop command during active timing.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # now TIMING
            (blind_set, "stop"),  # should be rejected
            (blind_set, _cal_cmd("mark")),  # continue calibration
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- stop pin NOT pressed by the "stop" command
        # The only presses should be from calibration go (down pin)
        stop_presses = [p for p in fake_gpio.presses if p.pin == BLIND_CFG.pin_stop]
        assert len(stop_presses) == 0, (
            f"Stop pin should not be pressed during calibration TIMING; "
            f"got {len(stop_presses)} presses"
        )


# ---------------------------------------------------------------------------
# Cross-cover isolation
# ---------------------------------------------------------------------------


class TestCalibrationCoverIsolation:
    """Calibration on one cover does not affect the other."""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_second_cover_accepts_commands_during_first_cover_calibration(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Window accepts open command while blind is calibrating.

        Technique: Integration -- verify per-cover calibration state isolation.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"
        window_set = f"{TOPIC_PREFIX}/window/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),  # blind enters calibration
            (window_set, "open"),  # window should work
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- window up pin pressed (command accepted)
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert WINDOW_CFG.pin_up in pressed_pins, (
            f"Window up pin {WINDOW_CFG.pin_up} should be pressed; got: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_second_cover_has_no_calibration_state(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Window has no calibration state messages when only blind calibrates.

        Technique: Specification-based -- calibration topics are per-cover.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
            (blind_set, _cal_cmd("go")),
            (blind_set, _cal_cmd("mark")),
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- blind has calibration state, window does not
        blind_states = _get_cal_states(mock_mqtt, "blind")
        window_states = _get_cal_states(mock_mqtt, "window")
        assert len(blind_states) >= 5, "Blind should have calibration states"
        assert len(window_states) == 0, (
            f"Window should have no calibration state messages; got: {window_states}"
        )

        # Assert -- window has no calibration result
        window_results = _get_cal_results(mock_mqtt, "window")
        assert len(window_results) == 0
