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
    GROUP_SUMMARIES,
    INTERVAL_ATTR,
    make_telemetry_handler,
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
def mock_app() -> MagicMock:
    """App mock with a tracked add_telemetry."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Spec-table tests for INTERVAL_ATTR / GROUP_SUMMARIES
# ---------------------------------------------------------------------------


class TestTelemetrySpecs:
    """Verify that INTERVAL_ATTR and GROUP_SUMMARIES cover all SIGNAL_GROUPS."""

    def test_interval_attr_covers_all_signal_groups(self) -> None:
        """INTERVAL_ATTR must have one entry per SIGNAL_GROUPS key.

        Technique: Specification-based — every group needs a polling interval.
        """
        assert set(INTERVAL_ATTR.keys()) == set(SIGNAL_GROUPS.keys())

    def test_group_summaries_covers_all_signal_groups(self) -> None:
        """GROUP_SUMMARIES must have one entry per SIGNAL_GROUPS key.

        Technique: Specification-based — every group needs a human-readable summary.
        """
        assert set(GROUP_SUMMARIES.keys()) == set(SIGNAL_GROUPS.keys())

    @pytest.mark.parametrize("group", list(SIGNAL_GROUPS.keys()))
    def test_interval_attr_values_are_strings(self, group: str) -> None:
        """Each INTERVAL_ATTR value must be a non-empty string (settings attr)."""
        value = INTERVAL_ATTR[group]
        assert isinstance(value, str) and value

    @pytest.mark.parametrize("group", list(SIGNAL_GROUPS.keys()))
    def test_group_summary_values_are_strings(self, group: str) -> None:
        """Each GROUP_SUMMARIES value must be a non-empty string."""
        value = GROUP_SUMMARIES[group]
        assert isinstance(value, str) and value


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
        handler = make_telemetry_handler(group)
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
        handler = make_telemetry_handler(group)
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
        handler = make_telemetry_handler("outdoor")
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
        handler = make_telemetry_handler("system")
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
        handler = make_telemetry_handler("diagnosis")
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
        handler = make_telemetry_handler("heating_floor")
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
        handler_outdoor = make_telemetry_handler("outdoor")
        handler_hot_water = make_telemetry_handler("hot_water")

        fake = FakeOptolinkAdapter()
        result_outdoor = await handler_outdoor(port=fake)
        result_hot_water = await handler_hot_water(port=fake)

        assert set(result_outdoor.keys()) == set(SIGNAL_GROUPS["outdoor"])
        assert set(result_hot_water.keys()) == set(SIGNAL_GROUPS["hot_water"])
        assert set(result_outdoor.keys()) != set(result_hot_water.keys())
