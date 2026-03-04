# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Unit tests for devices/commands.py — Command handler registration.

Test Techniques Used:
- Specification-based: Verify registration contract and handler behaviour
- Equivalence Partitioning: Valid vs invalid payloads, empty vs populated
- Error Guessing: Malformed JSON, unknown signals, non-dict payloads
- Cross-reference: Handler dispatches write_signal for each payload key
- Parametrize: All 4 command groups covered
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices import COMMAND_GROUPS
from vito2mqtt.devices.commands import (
    _make_handler,
    _validate_payload,
    register_commands,
)
from vito2mqtt.errors import InvalidSignalError
from vito2mqtt.optolink.commands import COMMANDS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(monkeypatch: pytest.MonkeyPatch) -> Vito2MqttSettings:
    """Construct Vito2MqttSettings with the required env var set."""
    monkeypatch.setenv("VITO2MQTT_SERIAL_PORT", "/dev/ttyUSB0")
    return Vito2MqttSettings()


@pytest.fixture()
def mock_app(settings: Vito2MqttSettings) -> MagicMock:
    """App mock with a real settings instance and a tracked add_command."""
    app = MagicMock()
    app.settings = settings
    return app


# ---------------------------------------------------------------------------
# register_commands
# ---------------------------------------------------------------------------


class TestRegisterCommands:
    """Verify register_commands wires up all 4 command groups."""

    def test_rejects_wrong_settings_type(self) -> None:
        """Must raise TypeError when app.settings is not Vito2MqttSettings.

        Technique: Error Guessing — guard clause protects against misconfigured app.
        """
        app = MagicMock()
        app.settings = object()  # Not Vito2MqttSettings

        with pytest.raises(TypeError, match="Expected Vito2MqttSettings"):
            register_commands(app)

    def test_registers_all_four_groups(self, mock_app: MagicMock) -> None:
        """Must call add_command exactly once per command group.

        Technique: Specification-based — one handler per group.
        """
        register_commands(mock_app)

        assert mock_app.add_command.call_count == 4

        registered_names = {
            call.kwargs["name"] for call in mock_app.add_command.call_args_list
        }
        assert registered_names == set(COMMAND_GROUPS.keys())

    def test_handler_functions_are_callable(self, mock_app: MagicMock) -> None:
        """Each registered func must be a callable (the handler closure).

        Technique: Specification-based — func must be async callable.
        """
        register_commands(mock_app)

        for call in mock_app.add_command.call_args_list:
            assert callable(call.kwargs["func"]), (
                f"Group {call.kwargs['name']!r}: func is not callable"
            )


# ---------------------------------------------------------------------------
# _validate_payload
# ---------------------------------------------------------------------------


class TestValidatePayload:
    """Verify payload parsing and validation logic."""

    def test_valid_payload_returns_dict(self) -> None:
        """A single-key payload with a known signal parses correctly.

        Technique: Specification-based — happy path for valid JSON.
        """
        group = "hot_water"
        first_signal = COMMAND_GROUPS[group][0]
        raw = json.dumps({first_signal: 42})

        result = _validate_payload(raw, group)

        assert isinstance(result, dict)
        assert result == {first_signal: 42}

    def test_invalid_json_raises(self) -> None:
        """Malformed JSON must raise InvalidSignalError.

        Technique: Error Guessing — broken JSON string.
        """
        with pytest.raises(InvalidSignalError, match="Invalid JSON payload"):
            _validate_payload("{bad", "hot_water")

    def test_non_dict_payload_raises(self) -> None:
        """A JSON array (non-dict) must raise InvalidSignalError.

        Technique: Equivalence Partitioning — non-object JSON types.
        """
        with pytest.raises(InvalidSignalError, match="Expected JSON object"):
            _validate_payload("[1,2,3]", "hot_water")

    def test_unknown_signal_raises(self) -> None:
        """Payload with an unknown key must raise InvalidSignalError.

        Technique: Error Guessing — unknown signal name in payload.
        """
        with pytest.raises(InvalidSignalError, match="fake_signal"):
            _validate_payload('{"fake_signal": 42}', "hot_water")

    def test_empty_dict_returns_empty(self) -> None:
        """An empty JSON object must return an empty dict (no-op scenario).

        Technique: Equivalence Partitioning — boundary case, empty input.
        """
        result = _validate_payload("{}", "hot_water")
        assert result == {}

    def test_multiple_valid_keys(self) -> None:
        """Payload with two valid keys returns both.

        Technique: Specification-based — multiple signals in one payload.
        """
        group = "hot_water"
        signals = COMMAND_GROUPS[group][:2]
        raw = json.dumps({signals[0]: 42, signals[1]: 10})

        result = _validate_payload(raw, group)

        assert set(result.keys()) == set(signals)


# ---------------------------------------------------------------------------
# _make_handler — parametrized across all groups
# ---------------------------------------------------------------------------


class TestMakeHandler:
    """Verify handler closures produced by _make_handler."""

    @pytest.mark.parametrize(
        "group",
        list(COMMAND_GROUPS.keys()),
        ids=list(COMMAND_GROUPS.keys()),
    )
    async def test_handler_writes_single_signal(self, group: str) -> None:
        """Handler must dispatch write_signal for a single payload key.

        Technique: Cross-reference — handler calls port.write_signal
        with correct signal name and deserialized value.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler(group)

        first_signal = COMMAND_GROUPS[group][0]
        type_code = COMMANDS[first_signal].type_code

        # Pick a representative value based on type code.
        value = _test_value_for_type(type_code)
        payload = json.dumps({first_signal: value})

        await handler(payload=payload, port=fake)

        assert first_signal in fake.writes, (
            f"Expected write for {first_signal!r}, got writes: {fake.writes}"
        )

    async def test_handler_writes_multiple_signals(self) -> None:
        """Handler must write all signals present in the payload.

        Technique: Cross-reference — each payload key triggers a write.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler("hot_water")

        # hot_water_setpoint (IUNON) and hot_water_pump_overrun (IUNON)
        payload = json.dumps(
            {
                "hot_water_setpoint": 55,
                "hot_water_pump_overrun": 120,
            }
        )

        await handler(payload=payload, port=fake)

        assert fake.writes["hot_water_setpoint"] == 55
        assert fake.writes["hot_water_pump_overrun"] == 120

    async def test_handler_returns_none(self) -> None:
        """Handler must always return None (eventual consistency).

        Technique: Specification-based — commands don't publish state.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler("hot_water")

        payload = json.dumps({"hot_water_setpoint": 50})
        result = await handler(payload=payload, port=fake)

        assert result is None

    async def test_empty_payload_is_noop(self) -> None:
        """An empty JSON object must return None with no writes.

        Technique: Equivalence Partitioning — empty payload boundary.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler("hot_water")

        result = await handler(payload="{}", port=fake)

        assert result is None
        assert fake.writes == {}

    async def test_handler_writes_validated_ct_schedule(self) -> None:
        """CT signal: valid CycleTimeSchedule structure is written.

        Technique: Cross-reference — CT type code triggers
        _deserialize_cycle_time which validates the nested structure
        before passing it to write_signal.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler("hot_water")

        schedule = [
            [[8, 0], [22, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]
        payload = json.dumps({"timer_hw_monday": schedule})

        await handler(payload=payload, port=fake)

        assert "timer_hw_monday" in fake.writes
        assert fake.writes["timer_hw_monday"] == schedule

    async def test_invalid_json_raises_invalid_signal_error(self) -> None:
        """Malformed JSON in handler must raise InvalidSignalError.

        Technique: Error Guessing — broken payload passed to handler.
        """
        handler = _make_handler("hot_water")
        fake = FakeOptolinkAdapter()

        with pytest.raises(InvalidSignalError, match="Invalid JSON payload"):
            await handler(payload="{bad", port=fake)

    async def test_unknown_signal_raises_invalid_signal_error(self) -> None:
        """Unknown key in handler payload must raise InvalidSignalError.

        Technique: Error Guessing — payload with non-existent signal.
        """
        handler = _make_handler("hot_water")
        fake = FakeOptolinkAdapter()

        payload = json.dumps({"nonexistent_signal": 99})

        with pytest.raises(InvalidSignalError, match="nonexistent_signal"):
            await handler(payload=payload, port=fake)


# ---------------------------------------------------------------------------
# Late-binding closure regression
# ---------------------------------------------------------------------------


class TestHandlerClosureIsolation:
    """Ensure factory avoids the late-binding closure pitfall."""

    async def test_handlers_capture_different_groups(self) -> None:
        """Two handlers for different groups must dispatch to different signals.

        Technique: Error Guessing — classic late-binding closure bug.
        """
        handler_hot_water = _make_handler("hot_water")
        handler_system = _make_handler("system")

        fake_hw = FakeOptolinkAdapter()
        fake_sys = FakeOptolinkAdapter()

        # Write one signal from each group.
        payload_hw = json.dumps({"hot_water_setpoint": 55})
        payload_sys = json.dumps(
            {
                "timer_cp_monday": [
                    [[8, 0], [22, 0]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                    [[None, None], [None, None]],
                ]
            }
        )

        await handler_hot_water(payload=payload_hw, port=fake_hw)
        await handler_system(payload=payload_sys, port=fake_sys)

        assert "hot_water_setpoint" in fake_hw.writes
        assert "timer_cp_monday" in fake_sys.writes

        # Cross-check: the hot_water handler didn't write system signals.
        assert "timer_cp_monday" not in fake_hw.writes
        assert "hot_water_setpoint" not in fake_sys.writes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _test_value_for_type(type_code: str) -> object:
    """Return a representative JSON-safe test value for a type code."""
    values: dict[str, object] = {
        "IS10": 20.5,
        "IUNON": 42,
        "IU3600": 1.5,
        "PR2": 128,
        "PR3": 50.0,
        "BA": "shutdown",
        "USV": "undefined",
        "CT": [
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ],
        "TI": "2026-03-04T12:00:00",
    }
    return values.get(type_code, 0)
