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

"""Unit tests for devices/telemetry.py — Telemetry handler registration.

Test Techniques Used:
- Specification-based: Verify registration contract and handler behaviour
- Cross-reference: Handler output matches SIGNAL_GROUPS × COMMANDS × serialize_value
- Equivalence Partitioning: Passthrough vs. converted type codes
- Parametrize: All 7 groups covered by a single parametrized test
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from vito2mqtt.adapters.fake import FakeOptolinkAdapter
from vito2mqtt.config import Vito2MqttSettings
from vito2mqtt.devices import SIGNAL_GROUPS
from vito2mqtt.devices._serialization import serialize_value
from vito2mqtt.devices.telemetry import (
    _INTERVAL_ATTR,
    _get_interval,
    _make_handler,
    register_telemetry,
)
from vito2mqtt.optolink.codec import ReturnStatus
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
    """App mock with a real settings instance and a tracked add_telemetry."""
    app = MagicMock()
    app.settings = settings
    return app


# ---------------------------------------------------------------------------
# register_telemetry
# ---------------------------------------------------------------------------


class TestRegisterTelemetry:
    """Verify register_telemetry wires up all 7 signal groups."""

    def test_rejects_wrong_settings_type(self) -> None:
        """Must raise TypeError when app.settings is not Vito2MqttSettings.

        Technique: Error Guessing — guard clause protects against misconfigured app.
        """
        app = MagicMock()
        app.settings = object()  # Not Vito2MqttSettings

        with pytest.raises(TypeError, match="Expected Vito2MqttSettings"):
            register_telemetry(app)

    def test_registers_all_seven_groups(self, mock_app: MagicMock) -> None:
        """Must call add_telemetry exactly once per signal group.

        Technique: Specification-based — one handler per group.
        """
        register_telemetry(mock_app)

        assert mock_app.add_telemetry.call_count == 7

        registered_names = {
            call.kwargs["name"] for call in mock_app.add_telemetry.call_args_list
        }
        assert registered_names == set(SIGNAL_GROUPS.keys())

    def test_uses_settings_polling_intervals(
        self, mock_app: MagicMock, settings: Vito2MqttSettings
    ) -> None:
        """Each group's interval must come from the matching settings field.

        Technique: Cross-reference — intervals match _INTERVAL_ATTR mapping.
        """
        register_telemetry(mock_app)

        for call in mock_app.add_telemetry.call_args_list:
            group = call.kwargs["name"]
            expected = getattr(settings, _INTERVAL_ATTR[group])
            assert call.kwargs["interval"] == expected, (
                f"Group {group!r}: expected interval {expected}, "
                f"got {call.kwargs['interval']}"
            )

    def test_uses_on_change_publish_strategy(self, mock_app: MagicMock) -> None:
        """Every registration must use an OnChange publish strategy.

        Technique: Specification-based — architecture requires OnChange.
        """
        from cosalette import OnChange

        register_telemetry(mock_app)

        for call in mock_app.add_telemetry.call_args_list:
            assert isinstance(call.kwargs["publish"], OnChange), (
                f"Group {call.kwargs['name']!r}: "
                f"expected OnChange, got {type(call.kwargs['publish'])}"
            )

    def test_uses_optolink_coalescing_group(self, mock_app: MagicMock) -> None:
        """Every handler must be registered with group="optolink".

        Technique: Specification-based — ADR-007 requires coalescing
        via the "optolink" group for all signal handlers.
        """
        register_telemetry(mock_app)

        for call in mock_app.add_telemetry.call_args_list:
            assert call.kwargs["group"] == "optolink", (
                f"Group {call.kwargs['name']!r}: "
                f"expected group='optolink', got {call.kwargs.get('group')!r}"
            )

    def test_handler_functions_are_callable(self, mock_app: MagicMock) -> None:
        """Each registered func must be a callable (the handler closure).

        Technique: Specification-based — func must be async callable.
        """
        register_telemetry(mock_app)

        for call in mock_app.add_telemetry.call_args_list:
            assert callable(call.kwargs["func"]), (
                f"Group {call.kwargs['name']!r}: func is not callable"
            )


# ---------------------------------------------------------------------------
# _get_interval
# ---------------------------------------------------------------------------


class TestGetInterval:
    """Verify _get_interval maps groups to settings fields correctly."""

    @pytest.mark.parametrize(
        ("group", "attr"),
        list(_INTERVAL_ATTR.items()),
        ids=list(_INTERVAL_ATTR.keys()),
    )
    def test_returns_correct_interval_per_group(
        self,
        settings: Vito2MqttSettings,
        group: str,
        attr: str,
    ) -> None:
        """Each group must resolve to the correct settings attribute.

        Technique: Specification-based — _INTERVAL_ATTR defines the mapping.
        """
        expected = getattr(settings, attr)
        assert _get_interval(settings, group) == expected

    def test_interval_attr_covers_all_groups(self) -> None:
        """_INTERVAL_ATTR must have an entry for every signal group.

        Technique: Cross-reference — SIGNAL_GROUPS ↔ _INTERVAL_ATTR.
        """
        assert set(_INTERVAL_ATTR.keys()) == set(SIGNAL_GROUPS.keys())


# ---------------------------------------------------------------------------
# _make_handler — parametrized across all groups
# ---------------------------------------------------------------------------


class TestMakeHandler:
    """Verify handler closures produced by _make_handler."""

    @pytest.mark.parametrize(
        "group",
        list(SIGNAL_GROUPS.keys()),
        ids=list(SIGNAL_GROUPS.keys()),
    )
    async def test_handler_returns_dict_with_all_group_signals(
        self, group: str
    ) -> None:
        """Handler must return a dict keyed by every signal in the group.

        Technique: Specification-based — handler must read all group signals.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler(group)
        result = await handler(port=fake)

        assert isinstance(result, dict)
        assert set(result.keys()) == set(SIGNAL_GROUPS[group])

    @pytest.mark.parametrize(
        "group",
        list(SIGNAL_GROUPS.keys()),
        ids=list(SIGNAL_GROUPS.keys()),
    )
    async def test_handler_values_match_serialized_defaults(self, group: str) -> None:
        """Each value must be the serialized form of the fake adapter default.

        Technique: Cross-reference — handler output matches
        serialize_value(fake_default, type_code) for every signal.
        """
        fake = FakeOptolinkAdapter()
        handler = _make_handler(group)
        result = await handler(port=fake)

        # Read the raw defaults independently for comparison.
        raw = await fake.read_signals(SIGNAL_GROUPS[group])

        for name, value in result.items():
            type_code = COMMANDS[name].type_code
            expected = serialize_value(raw[name], type_code)
            assert value == expected, (
                f"Signal {name!r} (type {type_code}): "
                f"got {value!r}, expected {expected!r}"
            )


# ---------------------------------------------------------------------------
# Handler serialization integration — specific type codes
# ---------------------------------------------------------------------------


class TestHandlerSerializationIntegration:
    """Verify handlers correctly serialize non-passthrough type codes."""

    async def test_passthrough_types_unchanged(self) -> None:
        """IS10 signals pass through as-is (no conversion).

        Technique: Equivalence Partitioning — passthrough group.
        """
        responses = {
            "outdoor_temperature": 5.2,
            "outdoor_temperature_lowpass": 4.8,
            "outdoor_temperature_damped": 5.0,
        }
        fake = FakeOptolinkAdapter(responses=responses)
        handler = _make_handler("outdoor")
        result = await handler(port=fake)

        assert result == responses

    async def test_return_status_serialized_to_lowercase(self) -> None:
        """RT signals serialize ReturnStatus members to lowercase strings.

        Technique: Specification-based — RT → name.lower().
        """
        responses: dict[str, object] = {
            sig: ReturnStatus.ON
            for sig in SIGNAL_GROUPS["system"]
            if COMMANDS[sig].type_code == "RT"
        }
        # Fill remaining signals with passthrough defaults.
        for sig in SIGNAL_GROUPS["system"]:
            if sig not in responses:
                responses[sig] = 20.5

        fake = FakeOptolinkAdapter(responses=responses)
        handler = _make_handler("system")
        result = await handler(port=fake)

        rt_signals = [
            s for s in SIGNAL_GROUPS["system"] if COMMANDS[s].type_code == "RT"
        ]
        for sig in rt_signals:
            assert result[sig] == "on", f"{sig}: expected 'on', got {result[sig]!r}"

    async def test_error_history_serialized_to_dict(self) -> None:
        """ES signals serialize [label, datetime] to structured dict.

        Technique: Specification-based — ES → {error, timestamp}.
        """
        ts = datetime(2025, 6, 15, 10, 30, 0)
        es_value = ["Sensor error", ts]

        responses: dict[str, object] = {
            "error_status": ReturnStatus.ERROR,
            "error_history_1": es_value,
        }
        # Fill remaining error_history signals.
        for sig in SIGNAL_GROUPS["diagnosis"]:
            if sig not in responses:
                responses[sig] = ["no error", datetime(2026, 1, 1)]

        fake = FakeOptolinkAdapter(responses=responses)
        handler = _make_handler("diagnosis")
        result = await handler(port=fake)

        assert result["error_status"] == "error"
        assert result["error_history_1"] == {
            "error": "Sensor error",
            "timestamp": "2025-06-15T10:30:00",
        }

    async def test_handler_with_mixed_types_in_heating_floor(self) -> None:
        """heating_floor group contains IS10, RT, PR2, IUNON, BA signals.

        Technique: Equivalence Partitioning — group with diverse type codes.
        """
        responses: dict[str, object] = {
            "flow_temperature_m2": 35.5,  # IS10 → passthrough
            "flow_temperature_setpoint_m2": 40.0,  # IS10 → passthrough
            "pump_status_m2": ReturnStatus.ON,  # RT → "on"
            "pump_speed_m2": 80,  # PR2 → passthrough
            "frost_warning_m2": 0,  # IUNON → passthrough
            "frost_limit_m2": -5,  # IUNON → passthrough
            "operating_mode_m2": "normal",  # BA → passthrough
            "operating_mode_economy_m2": "economy",  # BA → passthrough
        }

        fake = FakeOptolinkAdapter(responses=responses)
        handler = _make_handler("heating_floor")
        result = await handler(port=fake)

        assert result["flow_temperature_m2"] == 35.5
        assert result["pump_status_m2"] == "on"
        assert result["pump_speed_m2"] == 80
        assert result["operating_mode_m2"] == "normal"


# ---------------------------------------------------------------------------
# Late-binding closure regression
# ---------------------------------------------------------------------------


class TestHandlerClosureIsolation:
    """Ensure factory avoids the late-binding closure pitfall."""

    async def test_handlers_capture_different_groups(self) -> None:
        """Two handlers for different groups must read different signals.

        Technique: Error Guessing — classic late-binding closure bug.
        """
        handler_outdoor = _make_handler("outdoor")
        handler_hot_water = _make_handler("hot_water")

        fake = FakeOptolinkAdapter()
        result_outdoor = await handler_outdoor(port=fake)
        result_hot_water = await handler_hot_water(port=fake)

        assert set(result_outdoor.keys()) == set(SIGNAL_GROUPS["outdoor"])
        assert set(result_hot_water.keys()) == set(SIGNAL_GROUPS["hot_water"])
        assert set(result_outdoor.keys()) != set(result_hot_water.keys())
