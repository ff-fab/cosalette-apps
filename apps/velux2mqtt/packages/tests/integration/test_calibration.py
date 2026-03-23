"""Integration tests for velux2mqtt calibration end-to-end flow.

Exercises the full calibration MQTT ping-pong through the real app wiring:
start calibration on one cover, send go/mark commands for multiple runs in
each direction (with offset marks), verify status messages at each step,
verify final results published (including avg_offset), verify normal commands
rejected during calibration, and verify the second cover is unaffected.

Test Techniques Used:
- State Transition Testing: Full calibration lifecycle IDLE -> READY -> TIMING_OFFSET
  -> TIMING -> COMPLETE
- Integration Testing: Full app wiring with MQTT command delivery and GPIO interaction
- Specification-based: MQTT topic payloads, calibration result format, direction
  alternation, offset measurement
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


def _cal_direction_cmds(topic: str) -> list[tuple[str, str]]:
    """Build the 3-step command sequence for one direction: go, mark(offset), mark(travel)."""
    return [
        (topic, _cal_cmd("go")),
        (topic, _cal_cmd("mark")),  # offset mark
        (topic, _cal_cmd("mark")),  # travel mark
    ]


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

        Technique: State Transition Testing -- IDLE -> READY -> TIMING_OFFSET -> TIMING
        -> READY -> TIMING_OFFSET -> TIMING -> COMPLETE, verifying each published state.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # Act -- full single-run calibration sequence (go + mark-offset + mark-travel)
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            *_cal_direction_cmds(blind_set),  # close direction
            *_cal_direction_cmds(blind_set),  # open direction
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- calibration states published in order
        states = _get_cal_states(mock_mqtt, "blind")
        assert len(states) == 7, (
            f"Expected 7 state messages, got {len(states)}: {states}"
        )

        # Step 1: start -> READY, run=1, direction=CLOSE
        assert states[0]["state"] == "READY"
        assert states[0]["run"] == 1
        assert states[0]["direction"] == "CLOSE"

        # Step 2: go -> TIMING_OFFSET
        assert states[1]["state"] == "TIMING_OFFSET"

        # Step 3: mark (offset) -> TIMING
        assert states[2]["state"] == "TIMING"

        # Step 4: mark (travel) -> READY (switches to OPEN)
        assert states[3]["state"] == "READY"
        assert states[3]["direction"] == "OPEN"

        # Step 5: go -> TIMING_OFFSET
        assert states[4]["state"] == "TIMING_OFFSET"

        # Step 6: mark (offset) -> TIMING
        assert states[5]["state"] == "TIMING"

        # Step 7: mark (travel) -> COMPLETE
        assert states[6]["state"] == "COMPLETE"

        # Assert -- result published with offset
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert "avg_close" in results[0]
        assert "avg_open" in results[0]
        assert "avg_offset" in results[0]
        assert isinstance(results[0]["avg_close"], float)
        assert isinstance(results[0]["avg_open"], float)
        assert isinstance(results[0]["avg_offset"], float)

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
        and final averaged result including offset.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # 2 runs: close/open, close/open (each with offset mark)
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=2)),
            # Run 1
            *_cal_direction_cmds(blind_set),
            *_cal_direction_cmds(blind_set),
            # Run 2
            *_cal_direction_cmds(blind_set),
            *_cal_direction_cmds(blind_set),
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

        # Assert -- result published with averaged values including offset
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 1
        assert results[0]["avg_close"] > 0
        assert results[0]["avg_open"] > 0
        assert results[0]["avg_offset"] >= 0

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
            *_cal_direction_cmds(blind_set),  # close -> down pin
            *_cal_direction_cmds(blind_set),  # open -> up pin
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

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_cancel_from_timing_offset_returns_to_idle(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Cancel during TIMING_OFFSET state returns to IDLE with no result.

        Technique: State Transition Testing -- cancel from TIMING_OFFSET -> IDLE.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # enter TIMING_OFFSET
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

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_cancel_from_timing_returns_to_idle(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
    ) -> None:
        """Cancel during TIMING state returns to IDLE with no result.

        Technique: State Transition Testing -- cancel from TIMING -> IDLE.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # Act -- start calibration, enter TIMING_OFFSET, mark offset -> TIMING, cancel
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # enter TIMING_OFFSET
            (blind_set, _cal_cmd("mark")),  # offset -> TIMING
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

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_start_without_explicit_runs_uses_default(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Start without explicit runs uses default calibration_runs from settings.

        Technique: Specification-based -- settings default (calibration_runs=3)
        flows through when start command omits runs parameter.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        # Arrange -- build commands for default 3 runs
        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start")),  # no runs parameter
        ]
        for _run in range(3):
            commands.extend(_cal_direction_cmds(blind_set))  # close
            commands.extend(_cal_direction_cmds(blind_set))  # open

        # Act
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- calibration completed successfully
        states = _get_cal_states(mock_mqtt, "blind")
        assert states[-1]["state"] == "COMPLETE", (
            f"Expected final state COMPLETE, got {states[-1]['state']}"
        )

        # Assert -- result published with averaged values including offset
        results = _get_cal_results(mock_mqtt, "blind")
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"
        assert "avg_close" in results[0]
        assert "avg_open" in results[0]
        assert "avg_offset" in results[0]
        assert isinstance(results[0]["avg_close"], float)
        assert isinstance(results[0]["avg_open"], float)
        assert isinstance(results[0]["avg_offset"], float)


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
        pressed_pins = [p.pin for p in fake_gpio.presses]
        assert BLIND_CFG.pin_up not in pressed_pins, (
            f"Up pin {BLIND_CFG.pin_up} should NOT be pressed during calibration; "
            f"got: {pressed_pins}"
        )

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_normal_command_rejected_during_timing_offset_state(
        self,
        integration_app_no_homing: App,
        mock_mqtt: MockMqttClient,
        test_settings_no_homing: Velux2MqttSettings,
        fake_gpio: FakeGpio,
    ) -> None:
        """Stop command is ignored while calibration is in TIMING_OFFSET state.

        Technique: Error Guessing -- stop command during offset timing.
        """
        blind_set = f"{TOPIC_PREFIX}/blind/set"

        commands: list[tuple[str, str]] = [
            (blind_set, _cal_cmd("start", runs=1)),
            (blind_set, _cal_cmd("go")),  # now TIMING_OFFSET
            (blind_set, "stop"),  # should be rejected
            (blind_set, _cal_cmd("mark")),  # continue to TIMING
            (blind_set, _cal_cmd("mark")),  # complete close travel
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- stop pin NOT pressed by the "stop" command
        stop_presses = [p for p in fake_gpio.presses if p.pin == BLIND_CFG.pin_stop]
        assert len(stop_presses) == 0, (
            f"Stop pin should not be pressed during calibration TIMING_OFFSET; "
            f"got {len(stop_presses)} presses"
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
            (blind_set, _cal_cmd("go")),  # now TIMING_OFFSET
            (blind_set, _cal_cmd("mark")),  # now TIMING
            (blind_set, "stop"),  # should be rejected
            (blind_set, _cal_cmd("mark")),  # complete close travel
        ]
        await run_app_with_commands(
            integration_app_no_homing,
            mock_mqtt,
            test_settings_no_homing,
            commands,
        )

        # Assert -- stop pin NOT pressed by the "stop" command
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
            *_cal_direction_cmds(blind_set),  # close
            *_cal_direction_cmds(blind_set),  # open
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
        assert len(blind_states) == 7, "Blind should have calibration states"
        assert len(window_states) == 0, (
            f"Window should have no calibration state messages; got: {window_states}"
        )

        # Assert -- window has no calibration result
        window_results = _get_cal_results(mock_mqtt, "window")
        assert len(window_results) == 0
